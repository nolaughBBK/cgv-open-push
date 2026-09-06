from datetime import datetime

from curl_cffi import requests


BASE_URL = "https://cgv.co.kr"

BOOKING_PAGE_URL = f"{BASE_URL}/cnm/movieBook"

SCHEDULE_API_URL = (
    f"{BASE_URL}/api/v1/booking/searchMovScnInfo"
)


class CGVClient:
    def __init__(self):
        self.session = requests.Session(
            impersonate="chrome"
        )

        self._initialize_session()

    def _initialize_session(self):
        """
        CGV 예매 페이지에 먼저 접속해서
        브라우저 세션과 쿠키를 생성한다.
        """

        response = self.session.get(
            BOOKING_PAGE_URL,
            timeout=20
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"CGV 예매 페이지 접속 실패: "
                f"{response.status_code}"
            )

    def get_schedule(
        self,
        theater_code: str,
        play_date: str
    ):
        """
        특정 CGV 극장의 특정 날짜 전체 상영시간표를 조회한다.

        theater_code:
            CGV 극장 코드
            예: 용산아이파크몰 = 0013

        play_date:
            YYYYMMDD
            예: 20260907
        """

        response = self.session.get(
            SCHEDULE_API_URL,
            params={
                "coCd": "A420",
                "siteNo": theater_code,
                "scnYmd": play_date,
                "rtctlScopCd": "08",
            },
            headers={
                "Accept": (
                    "application/json, "
                    "text/plain, */*"
                ),
                "Accept-Language": (
                    "ko-KR,ko;q=0.9,"
                    "en-US;q=0.8"
                ),
                "Referer": BOOKING_PAGE_URL,
            },
            timeout=20
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"CGV API 요청 실패: "
                f"{response.status_code}"
            )

        data = response.json()

        if data.get("statusCode") != 0:
            raise RuntimeError(
                f"CGV API 오류: "
                f"{data.get('statusMessage')}"
            )

        return data.get("data") or []


if __name__ == "__main__":
    client = CGVClient()

    today = datetime.now().strftime("%Y%m%d")

    schedules = client.get_schedule(
        theater_code="0013",
        play_date=today
    )

    print(
        f"용산아이파크몰 "
        f"{today} 상영 회차: "
        f"{len(schedules)}개"
    )

    print()

    for schedule in schedules[:20]:
        print(
            schedule.get("movNm"),
            "|",
            schedule.get("scnsNm"),
            "|",
            schedule.get("scnsrtTm"),
            "| 잔여석",
            schedule.get("frSeatCnt"),
            "/",
            schedule.get("stcnt")
        )