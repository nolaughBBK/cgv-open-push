from datetime import datetime, timedelta
import json
from pathlib import Path
import time

from app.config import THEATERS, MONITOR_DAYS
from app.cgv.client import CGVClient


STATE_FILE = Path("data/schedule_state.json")

# CGV 서버에 너무 빠르게 연속 요청하지 않도록 간격
REQUEST_DELAY = 0.3


def detect_format(screen_name: str):
    """
    상영관 이름에서 특별관 종류를 판별한다.
    """

    screen_name_upper = screen_name.upper()

    if "IMAX" in screen_name_upper:
        return "IMAX"

    if "4DX" in screen_name_upper:
        return "4DX"

    if "SCREENX" in screen_name_upper:
        return "SCREENX"

    return None


def filter_special_schedules(
    schedules,
    allowed_formats
):
    """
    전체 상영시간표 중 해당 극장에서
    감시하도록 설정한 특별관만 추출한다.
    """

    result = []

    for schedule in schedules:
        screen_name = (
            schedule.get("scnsNm") or ""
        )

        special_format = detect_format(
            screen_name
        )

        if special_format is None:
            continue

        # config.py에서 감시 대상으로 지정한 특별관만 허용
        if special_format not in allowed_formats:
            continue

        result.append(
            {
                "id": (
                    f"{schedule.get('scnYmd', '')}:"
                    f"{schedule.get('scnsNo', '')}:"
                    f"{schedule.get('scnSseq', '')}:"
                    f"{schedule.get('prodNo', '')}:"
                    f"{schedule.get('scnsrtTm', '')}"
                ),
                "format": special_format,
                "movie_name": (
                    schedule.get("movNm") or ""
                ),
                "screen_name": screen_name,
                "play_date": (
                    schedule.get("scnYmd") or ""
                ),
                "start_time": (
                    schedule.get("scnsrtTm") or ""
                ),
                "remaining_seats": (
                    schedule.get("frSeatCnt")
                ),
                "total_seats": (
                    schedule.get("stcnt")
                ),
            }
        )

    return result


def load_state():
    """
    이전 실행에서 저장한 상태를 읽는다.
    """

    if not STATE_FILE.exists():
        return {}

    try:
        with STATE_FILE.open(
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    except (
        json.JSONDecodeError,
        OSError
    ):
        return {}


def save_state(state):
    """
    현재 상태를 JSON 파일에 저장한다.
    """

    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with STATE_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2
        )


def find_new_schedules(
    state_key,
    schedules,
    state
):
    """
    이전 상태와 비교해서
    새로 추가된 상영 회차만 반환한다.
    """

    current_ids = {
        schedule["id"]
        for schedule in schedules
    }

    # 해당 극장/날짜를 처음 확인하는 경우
    # 현재 상태를 기준값으로만 저장
    if state_key not in state:
        state[state_key] = sorted(
            current_ids
        )

        return []

    previous_ids = set(
        state.get(state_key, [])
    )

    new_ids = (
        current_ids - previous_ids
    )

    new_schedules = [
        schedule
        for schedule in schedules
        if schedule["id"] in new_ids
    ]

    state[state_key] = sorted(
        current_ids
    )

    return new_schedules


def get_monitor_dates():
    """
    오늘부터 MONITOR_DAYS일 동안의
    YYYYMMDD 날짜 목록을 만든다.
    """

    today = datetime.now()

    return [
        (
            today + timedelta(days=day)
        ).strftime("%Y%m%d")
        for day in range(MONITOR_DAYS)
    ]


def cleanup_state(
    state,
    active_keys
):
    """
    현재 감시 범위를 벗어난 오래된 상태를 제거한다.
    """

    old_keys = [
        key
        for key in state
        if key not in active_keys
    ]

    for key in old_keys:
        del state[key]


def run_monitor():
    client = CGVClient()
    state = load_state()

    monitor_dates = get_monitor_dates()

    all_new_schedules = []
    active_keys = set()

    total_requests = 0
    total_special_schedules = 0

    print()
    print(
        f"CGV 특별관 감시 시작"
    )
    print(
        f"감시 극장: {len(THEATERS)}개"
    )
    print(
        f"감시 기간: {MONITOR_DAYS}일"
    )
    print("-" * 50)

    for theater_key, theater in THEATERS.items():

        print(
            f"\n[{theater['name']}] "
            f"{', '.join(theater['formats'])}"
        )

        for play_date in monitor_dates:

            state_key = (
                f"{theater_key}:{play_date}"
            )

            active_keys.add(state_key)

            try:
                schedules = client.get_schedule(
                    theater_code=theater["code"],
                    play_date=play_date
                )

                total_requests += 1

                special_schedules = (
                    filter_special_schedules(
                        schedules=schedules,
                        allowed_formats=(
                            theater["formats"]
                        )
                    )
                )

                total_special_schedules += (
                    len(special_schedules)
                )

                new_schedules = (
                    find_new_schedules(
                        state_key=state_key,
                        schedules=special_schedules,
                        state=state
                    )
                )

                print(
                    f"  {play_date} | "
                    f"전체 {len(schedules):3d} | "
                    f"특별관 "
                    f"{len(special_schedules):2d} | "
                    f"NEW "
                    f"{len(new_schedules):2d}"
                )

                for schedule in new_schedules:
                    schedule["theater_key"] = (
                        theater_key
                    )

                    schedule["theater_name"] = (
                        theater["name"]
                    )

                    all_new_schedules.append(
                        schedule
                    )

            except Exception as error:
                print(
                    f"  {play_date} | "
                    f"ERROR: {error}"
                )

            time.sleep(
                REQUEST_DELAY
            )

    cleanup_state(
        state=state,
        active_keys=active_keys
    )

    save_state(state)

    print()
    print("=" * 50)
    print(
        f"API 요청 완료: {total_requests}회"
    )
    print(
        f"현재 특별관 회차: "
        f"{total_special_schedules}개"
    )
    print(
        f"새로 발견된 회차: "
        f"{len(all_new_schedules)}개"
    )

    if not all_new_schedules:
        print(
            "\n새로 열린 특별관 "
            "상영 회차가 없습니다."
        )

    for schedule in all_new_schedules:
        print()
        print(
            f"[NEW]"
            f"[{schedule['format']}] "
            f"{schedule['theater_name']} "
            f"- {schedule['movie_name']}"
        )

        print(
            f"{schedule['play_date']} | "
            f"{schedule['screen_name']} | "
            f"{schedule['start_time']} | "
            f"잔여석 "
            f"{schedule['remaining_seats']}"
            f"/"
            f"{schedule['total_seats']}"
        )

    return all_new_schedules


if __name__ == "__main__":
    run_monitor()