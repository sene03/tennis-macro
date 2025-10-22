# ---------- 예외 -------------
class NoAvailablePreferredTime(Exception):
    """선호 시간들이 모두 예약 불가(disabled)일 때 발생"""
    pass

