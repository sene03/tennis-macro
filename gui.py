import threading
import datetime as dt
import keyring
import tkinter as tk
from tkinter import ttk, messagebox

from config import SERVICE_NAME
from driver import build_driver
from booking import login, open_write_page, try_select_time_and_submit, fast_retry_loop, compute_open_time, wait_until
from utils import NoAvailablePreferredTime

class TennisGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("테니스 예약 매크로")
        self.geometry("700x550")

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        # 계정
        ttk.Label(frm, text="아이디").grid(row=0, column=0, sticky="w", pady=4)
        self.entry_id = ttk.Entry(frm, width=30); self.entry_id.grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(frm, text="비밀번호").grid(row=1, column=0, sticky="w", pady=4)
        self.entry_pw = ttk.Entry(frm, show="*", width=30); self.entry_pw.grid(row=1, column=1, sticky="w", pady=4)

        self.save_cred = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, text="아이디/비번 저장", variable=self.save_cred).grid(row=2, column=1, sticky="w", pady=4)

        # 예약일 -> replace free text with datepicker (year/month/day Comboboxes)
        ttk.Label(frm, text="예약일").grid(row=3, column=0, sticky="w", pady=4)
        date_row = ttk.Frame(frm); date_row.grid(row=3, column=1, sticky="w", pady=4)
        # year combobox (current year and next year)
        cur_year = dt.date.today().year
        self.cb_year = ttk.Combobox(date_row, values=[str(cur_year), str(cur_year+1)], width=6, state="readonly")
        self.cb_year.set(str(cur_year))
        self.cb_year.grid(row=0, column=0, padx=(0,6))
        # month combobox
        self.cb_month = ttk.Combobox(date_row, values=[f"{m:02d}" for m in range(1,13)], width=4, state="readonly")
        self.cb_month.set(f"{dt.date.today().month:02d}")
        self.cb_month.grid(row=0, column=1, padx=(0,6))
        # day combobox (will be populated based on year/month)
        self.cb_day = ttk.Combobox(date_row, values=[f"{d:02d}" for d in range(1,32)], width=4, state="readonly")
        self.cb_day.set(f"{dt.date.today().day:02d}")
        self.cb_day.grid(row=0, column=2)
        # bind updates to month/year change to refresh day list and time slots
        self.cb_year.bind("<<ComboboxSelected>>", lambda e: self.on_date_change())
        self.cb_month.bind("<<ComboboxSelected>>", lambda e: self.on_date_change())

        # 면 선택
        ttk.Label(frm, text="테니스장 면(1/2/3)").grid(row=4, column=0, sticky="w", pady=4)
        self.entry_office = ttk.Entry(frm, width=10); self.entry_office.insert(0, "1")
        self.entry_office.grid(row=4, column=1, sticky="w", pady=4)

        # 시간 선택 (will be built dynamically based on season)
        ttk.Label(frm, text="선호 시간(복수 체크)").grid(row=5, column=0, sticky="nw", pady=4)
        self.time_vars = {}
        self.time_box = ttk.Frame(frm); self.time_box.grid(row=5, column=1, sticky="w", pady=4)
        # initial population based on today's month
        self.rebuild_time_slots()

        # 관내/관외
        ttk.Label(frm, text="주거지").grid(row=6, column=0, sticky="w", pady=4)
        self.resident = ttk.Combobox(frm, values=["관내", "관외"], state="readonly", width=10)
        self.resident.current(0); self.resident.grid(row=6, column=1, sticky="w", pady=4)

        # 연락처
        ttk.Label(frm, text="연락처").grid(row=8, column=0, sticky="w", pady=4)
        self.entry_phone = ttk.Entry(frm, width=20); self.entry_phone.grid(row=8, column=1, sticky="w", pady=4)

        # 동반
        ttk.Label(frm, text="동반 인원수(0~3)").grid(row=9, column=0, sticky="w", pady=4)
        self.entry_comp_cnt = ttk.Entry(frm, width=10); self.entry_comp_cnt.insert(0, "0")
        self.entry_comp_cnt.grid(row=9, column=1, sticky="w", pady=4)

        ttk.Label(frm, text="동반자명(콤마로 구분)").grid(row=10, column=0, sticky="w", pady=4)
        self.entry_comp_names = ttk.Entry(frm, width=40); self.entry_comp_names.grid(row=10, column=1, sticky="w", pady=4)

        # 로그
        ttk.Label(frm, text="로그").grid(row=13, column=0, sticky="nw", pady=4)
        self.log = tk.Text(frm, height=12, width=62); self.log.grid(row=13, column=1, sticky="w", pady=4)

        # 버튼
        btn_box = ttk.Frame(frm); btn_box.grid(row=14, column=1, sticky="e", pady=8)
        ttk.Button(btn_box, text="예약 실행", command=self.run_thread).grid(row=0, column=1, padx=5, pady=4)

        # 첫 실행 시 저장된 계정 로드
        self.load_creds(silent=True)

    # ---- date/time helpers ----

    def on_date_change(self):
        # refresh day values based on selected year/month
        try:
            y = int(self.cb_year.get())
            m = int(self.cb_month.get())
        except Exception:
            return
        # compute days in month
        if m == 12:
            next_month = dt.date(y+1, 1, 1)
        else:
            next_month = dt.date(y, m+1, 1)
        first = dt.date(y, m, 1)
        days = (next_month - first).days
        day_values = [f"{d:02d}" for d in range(1, days+1)]
        cur_day = self.cb_day.get()
        self.cb_day['values'] = day_values
        if cur_day not in day_values:
            self.cb_day.set(day_values[0])
        # also rebuild time slots because season may change when month changes
        self.rebuild_time_slots()

    def selected_date(self) -> dt.date:
        return dt.date(int(self.cb_year.get()), int(self.cb_month.get()), int(self.cb_day.get()))

    def is_winter(self, date_obj: dt.date) -> bool:
        # winter: November(11), December(12), January(1), February(2)
        return date_obj.month in (11, 12, 1, 2)

    def build_time_hours_for_date(self, date_obj: dt.date):
        # return list of hour strings with 2-hour steps depending on season
        if self.is_winter(date_obj):
            start, end = 7, 19
        else:
            start, end = 6, 20
        hours = list(range(start, end+1, 2))
        return [f"{h:02d}" for h in hours]

    def rebuild_time_slots(self):
        # clear existing widgets
        for child in self.time_box.winfo_children():
            child.destroy()
        # decide date to use for determining season: prefer selected date if valid, otherwise today
        try:
            date_obj = self.selected_date()
        except Exception:
            date_obj = dt.date.today()
        hours = self.build_time_hours_for_date(date_obj)
        self.time_vars = {}
        for ix, hh in enumerate(hours):
            var = tk.BooleanVar(value=False)
            self.time_vars[hh] = var
            ttk.Checkbutton(self.time_box, text=f"{hh}시", variable=var).grid(row=ix//4, column=ix%4, sticky="w", padx=4, pady=2)
    
    # ---- helpers ----

    def log_print(self, msg: str):
        self.log.insert("end", f"{dt.datetime.now().strftime('%H:%M:%S')}  {msg}\n")
        self.log.see("end")
        self.update_idletasks()

    def load_creds(self, silent: bool = False):
        try:
            saved_id = keyring.get_password(SERVICE_NAME, "user_id")
            saved_pw = keyring.get_password(SERVICE_NAME, "user_pw")
            if saved_id:
                self.entry_id.delete(0, "end"); self.entry_id.insert(0, saved_id)
            if saved_pw:
                self.entry_pw.delete(0, "end"); self.entry_pw.insert(0, saved_pw)
            if not silent:
                messagebox.showinfo("불러오기", "저장된 계정 정보를 불러왔습니다.")
        except Exception as e:
            if not silent:
                messagebox.showwarning("경고", f"자격증명 불러오기 실패: {e}")

    def save_creds(self, uid: str, pw: str):
        try:
            keyring.set_password(SERVICE_NAME, "user_id", uid)
            keyring.set_password(SERVICE_NAME, "user_pw", pw)
        except Exception as e:
            self.log_print(f"[경고] 자격증명 저장 실패: {e}")

    def run_thread(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        try:
            user_id = self.entry_id.get().strip()
            password = self.entry_pw.get().strip()
            if not user_id:
                messagebox.showerror("오류", "아이디를 입력하세요.")
                return
            if not password:
                messagebox.showerror("오류", "비밀번호를 입력하세요.")
                return
            if self.save_cred.get():
                self.save_creds(user_id, password)

            # 날짜
            try:
                target_date = self.selected_date()
            except Exception:
                messagebox.showerror("오류", "예약일을 선택하세요.")
                return

            office_no = int(self.entry_office.get().strip())
            preferred_times = [k for k, v in self.time_vars.items() if v.get()]

            form_data = {
                "resident": self.resident.get(),
                "phone": self.entry_phone.get().strip(),
                "companion_count": int(self.entry_comp_cnt.get().strip() or "0"),
                "companions": [s.strip() for s in self.entry_comp_names.get().split(",") if s.strip()]
            }

            # 입력값 검증
            if not preferred_times:
                messagebox.showerror("오류", "선호 시간을 하나 이상 선택하세요.")
                return
            if not form_data["phone"]:
                messagebox.showerror("오류", "연락처를 입력하세요.")
                return

            self.log_print(f"예약 준비: {target_date} (면 {office_no}), 선호시간 {preferred_times}")
            open_dt = compute_open_time(target_date)
            self.log_print(f"예약 오픈 예상 시각: {open_dt} (현재 {dt.datetime.now()})")

            driver = build_driver(headless=False)
            self.log_print("브라우저 준비 완료")

            # 미리 로그인
            self.log_print("로그인 시도 중...")
            login(driver, user_id, password)
            self.log_print("로그인 완료")

            # 오픈 시각까지 대기
            now = dt.datetime.now()
            if now < open_dt:
                self.log_print("오픈 시각까지 대기합니다...")
                wait_until(open_dt)
                self.log_print("오픈 시각 도달!")

            # 1차 시도
            self.log_print("작성 페이지 진입...")
            open_write_page(driver, office_no, target_date)
            try:
                success = try_select_time_and_submit(driver, preferred_times, form_data)
            except NoAvailablePreferredTime as e:
                self.log_print(f"❌ 예약 실패 — {str(e)}")
                messagebox.showwarning("실패", f"{str(e)}")
                return

            # 빠른 재시도는 '일반 실패'일 때만 수행
            if not success:
                self.log_print("1차 실패 → 빠른 재시도 시작")
                try:
                    success = fast_retry_loop(driver, office_no, target_date, preferred_times, form_data)
                except NoAvailablePreferredTime as e:
                    # 재시도 중에도 전부 disabled인 상태가 확인되면 즉시 중단
                    self.log_print(f"❌ 예약 실패 — {str(e)}")
                    messagebox.showwarning("실패", f"{str(e)}")
                    return
    
            if success:
                self.log_print("✅ 예약 성공(추정). 완료 페이지를 확인해 주세요.")
                messagebox.showinfo("성공", "예약 성공(추정) — 브라우저 화면을 확인해 주세요.")
            else:
                self.log_print("❌ 예약 실패 — 선호 시간이 모두 매진이거나 제출이 거부되었습니다.")
                messagebox.showwarning("실패", "예약에 실패했습니다. 선호 시간을 조정하거나 재시도해 보세요.")

        except Exception as e:
            self.log_print(f"[예외] {e}")
            messagebox.showerror("오류", str(e))
