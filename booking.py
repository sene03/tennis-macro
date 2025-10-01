import time
import datetime as dt
from typing import List

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

from config import LOGIN_URL, WRITE_URL_TMPL
from utils import TIME_VALUE_MAP, NoAvailablePreferredTime
from driver import hide_popups


# --------- 공용 유틸 ---------

def wait_until(target_dt: dt.datetime):
    """
    target_dt 까지 현재 PC 시각으로 대기
    """
    while True:
        now = dt.datetime.now()
        delta = (target_dt - now).total_seconds()
        if delta <= 0:
            return
        # 남은 시간이 3초 이내면 짧게, 아니면 1초씩 대기
        time.sleep(0.2 if delta < 3 else 1.0)

def compute_open_time(target_date: dt.date) -> dt.datetime:
    """
    예약 오픈 = 예약일의 15일 전 00:00
    → PC의 현재 로컬 시각 기준
    """
    open_day = target_date - dt.timedelta(days=15)
    return dt.datetime(open_day.year, open_day.month, open_day.day, 0, 0, 0)




# --------- 페이지 동작 ---------

def login(driver, user_id: str, password: str, timeout: int = 20):
    """로그인 페이지로 이동 → 로그인"""
    driver.get(LOGIN_URL)
    hide_popups(driver)

    wait = WebDriverWait(driver, timeout)
    id_input = wait.until(EC.presence_of_element_located((By.NAME, "mb_id")))
    pw_input = wait.until(EC.presence_of_element_located((By.NAME, "mb_password")))
    id_input.clear(); id_input.send_keys(user_id)
    pw_input.clear(); pw_input.send_keys(password)

    login_btn = driver.find_element(By.ID, "ol_submit")
    login_btn.click()
    time.sleep(1.0)
    hide_popups(driver)
    return True  # 필요시 상단 "로그아웃" 존재 여부로 성공 판정 로직 보강 가능



def open_write_page(driver, office_no: int, target_date: dt.date, timeout: int = 20):
    """예약 작성 페이지 open"""
    url = WRITE_URL_TMPL.format(office_no=office_no, date=target_date.strftime("%Y-%m-%d"))
    driver.get(url)
    hide_popups(driver)
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.ID, "fwrite")))
    return True



def parse_with_bs4(driver):
    """필요 시 BeautifulSoup 보조 파싱"""
    return BeautifulSoup(driver.page_source, "html.parser")



def pick_time(driver, preferred_hours: List[str], timeout: int = 10) -> bool:
    """
    preferred_hours: ["06","08",...]
    - 선호 시간 라디오가 존재하되 모두 disabled면 NoAvailablePreferredTime 발생
    - 하나라도 선택되면 True, (선호 시간이 DOM에 아예 없으면 False)
    """
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#booking_time")))

    seen_preferred = False          # 선호 시간 라디오를 발견했는지
    selectable_found = False        # 클릭 가능한 선호 슬롯을 찾았는지

    for hh in preferred_hours:
        val = TIME_VALUE_MAP.get(hh)
        if not val:
            continue

        radios = driver.find_elements(By.CSS_SELECTOR, f'input[type="radio"][name="wr_2"][value="{val}"]')
        if not radios:
            # 이 시간 값 자체가 없으면 그냥 다음 시간으로
            continue

        seen_preferred = True
        r = radios[0]

        # disabled 여부 확인
        if r.get_attribute("disabled") is not None:
            continue

        li = r.find_element(By.XPATH, "./ancestor::li[1]")
        li_class = (li.get_attribute("class") or "")
        if "disabled" in li_class:
            continue

        # 여기까지 왔으면 선택 가능
        selectable_found = True
        input_id = r.get_attribute("id")
        if input_id:
            labels = driver.find_elements(By.CSS_SELECTOR, f'label[for="{input_id}"]')
            if labels:
                driver.execute_script("arguments[0].click();", labels[0])
            else:
                driver.execute_script("arguments[0].click();", r)
        else:
            driver.execute_script("arguments[0].click();", r)

        if r.is_selected():
            return True

    # 선호 시간 라디오들은 있었는데 모두 disabled였다면 → 즉시 실패 신호
    if seen_preferred and not selectable_found:
        raise NoAvailablePreferredTime("선호한 시간대가 모두 예약 불가(disabled)입니다.")

    # 선호 시간이 DOM에 아예 없었던 경우(비정상 케이스) → 일반 실패(True/False 프로토콜 유지)
    return False



def fill_and_submit_form(
    driver,
    *,
    resident: str,         # "관내" | "관외"
    phone: str,            # wr_subject (9자 이상)
    companion_count: int,  # wr_5 select 0~3
    companions: List[str], # wr_6 (콤마 구분)
    timeout: int = 10
) -> bool:
    wait = WebDriverWait(driver, timeout)

    # 주거지
    radio = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, f'input[name="wr_4"][value="{resident}"]')))
    driver.execute_script("arguments[0].click();", radio)

    # 동반 인원수
    sel = Select(driver.find_element(By.NAME, "wr_5"))
    sel.select_by_value(str(companion_count))

    # 동반자명
    comp_input = driver.find_element(By.NAME, "wr_6")
    comp_input.clear()
    if companion_count > 0:
        comp_input.send_keys(", ".join(companions) if companions else "동반자미상")

    # 연락처
    tel = driver.find_element(By.NAME, "wr_subject")
    tel.clear(); tel.send_keys(phone)  # 페이지 JS가 길이 검증

    # 개인정보 동의
    agree = driver.find_element(By.ID, "agree")
    if not agree.is_selected():
        driver.execute_script("arguments[0].click();", agree)

    # 제출
    submit_btn = driver.find_element(By.ID, "btn_submit")
    driver.execute_script("arguments[0].click();", submit_btn)

    # write.php 탈출하면 성공으로 가정
    WebDriverWait(driver, 5).until(lambda d: "write.php" not in d.current_url)
    return True




def try_select_time_and_submit(driver, preferred_times, form_data, timeout: int = 10) -> bool:
    """시간 선택 → 폼 채움 → 제출. 실패 시 False / 선호 전부 불가면 NoAvailablePreferredTime 예외 전달"""
    _hide(driver)
    # pick_time에서 NoAvailablePreferredTime이 발생하면 그대로 상위로 전달
    picked = pick_time(driver, preferred_times, timeout=timeout)
    if not picked:
        return False

    try:
        return fill_and_submit_form(
            driver,
            resident=form_data["resident"],
            phone=form_data["phone"],
            companion_count=int(form_data.get("companion_count", 0)),
            companions=form_data.get("companions", []),
            timeout=timeout
        )
    except Exception:
        return False




def fast_retry_loop(driver, office_no, target_date, preferred_times, form_data, retry_seconds: int = 60) -> bool:
    """오픈 직후 경쟁 상황에서
    retry_seconds 동안 0.3초 간격으로 재시도"""
    end_t = time.time() + retry_seconds
    while time.time() < end_t:
        open_write_page(driver, office_no, target_date)
        if try_select_time_and_submit(driver, preferred_times, form_data):
            return True
        time.sleep(0.3)  # 과도 트래픽 방지
    return False

# 내부 전용: 팝업 숨김
def _hide(driver):
    try:
        driver.execute_script("""
            document.querySelectorAll('#popup, .pop').forEach(el => el.style.display='none');
        """)
    except Exception:
        pass
