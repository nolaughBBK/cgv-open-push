from datetime import datetime, timedelta
import json
from pathlib import Path
import time

from app.config import (
    THEATERS,
    MONITOR_DAYS,
)

from app.cgv.client import CGVClient

from app.storage import (
    get_active_monitor_targets,
    track_seat_changes,
)


STATE_FILE = Path(
    "data/schedule_state.json"
)

THEATER_DELAY = 0.0

def detect_format(
    screen_name: str
):
    """
    CGV 상영관 이름에서
    특별관 종류를 판별한다.
    """

    screen_name = (
        screen_name or ""
    ).upper()

    if "IMAX" in screen_name:
        return "IMAX"

    if "4DX" in screen_name:
        return "4DX"

    if "SCREENX" in screen_name:
        return "SCREENX"

    return None


def filter_special_schedules(
    schedules,
    allowed_formats
):
    """
    지정된 특별관의 상영 회차만 추출한다.
    """

    result = []

    allowed_formats = set(
        allowed_formats
    )

    for schedule in schedules:

        screen_name = (
            schedule.get("scnsNm")
            or ""
        )

        special_format = (
            detect_format(
                screen_name
            )
        )

        if special_format is None:
            continue

        if (
            special_format
            not in allowed_formats
        ):
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

                "format":
                    special_format,

                "movie_name":
                    schedule.get("movNm")
                    or "",

                "screen_name":
                    screen_name,

                "play_date":
                    schedule.get("scnYmd")
                    or "",

                "start_time":
                    schedule.get("scnsrtTm")
                    or "",

                "remaining_seats":
                    schedule.get(
                        "frSeatCnt"
                    ),

                "total_seats":
                    schedule.get(
                        "stcnt"
                    ),
            }
        )

    return result


def load_state():
    """
    이전 감시 상태를 불러온다.
    """

    if not STATE_FILE.exists():
        return {}

    try:

        return json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

    except (
        json.JSONDecodeError,
        OSError
    ):

        return {}


def save_state(
    state
):
    """
    현재 감시 상태를 저장한다.
    """

    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATE_FILE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def find_new_schedules(
    state_key,
    schedules,
    state,
    alert_on_first_seen=False,
):
    """
    이전 상태와 현재 상태를 비교해
    새로 생긴 회차를 찾는다.
    """

    current_ids = {
        schedule["id"]
        for schedule in schedules
    }

    if state_key not in state:

        state[state_key] = sorted(
            current_ids
        )

        if alert_on_first_seen:
            return schedules

        return []

    previous_ids = set(
        state.get(
            state_key,
            []
        )
    )

    new_ids = (
        current_ids
        - previous_ids
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
    오늘부터 MONITOR_DAYS만큼
    감시 날짜를 생성한다.
    """

    today = datetime.now()

    return [
        (
            today
            + timedelta(days=day)
        ).strftime(
            "%Y%m%d"
        )

        for day in range(
            MONITOR_DAYS
        )
    ]


def make_subscription_id(
    theater_key,
    special_format
):
    return (
        f"{theater_key}|"
        f"{special_format}"
    )


def cleanup_state(
    state,
    active_keys
):
    """
    현재 구독하지 않는 특별관이나
    감시 범위를 벗어난 날짜 상태를 삭제한다.

    __ 로 시작하는 값은
    메타데이터이므로 유지한다.
    """

    for state_key in list(
        state.keys()
    ):

        if state_key.startswith(
            "__"
        ):
            continue

        if state_key not in active_keys:
            del state[state_key]


def run_monitor():
    """
    실제 구독자가 선택한
    극장 / 특별관 / 날짜만 감시한다.
    """

    state = load_state()

    monitor_dates = (
        get_monitor_dates()
    )

    active_targets = (
        get_active_monitor_targets(
            monitor_dates
        )
    )

    print()
    print(
        "CGV 특별관 감시 시작"
    )

    print(
        f"활성 구독 극장: "
        f"{len(active_targets)}개"
    )

    request_target_count = sum(
        len(date_targets)
        for date_targets
        in active_targets.values()
    )

    print(
        f"이번 조회 대상: "
        f"{request_target_count}회"
    )

    print(
        f"최대 감시 기간: "
        f"{MONITOR_DAYS}일"
    )

    print(
        "-" * 50
    )

    # 아무도 구독하지 않는 경우
    if not active_targets:

        print(
            "현재 활성 구독이 없습니다."
        )

        print(
            "CGV API 요청을 생략합니다."
        )

        cleanup_state(
            state,
            set()
        )

        state.pop(
            "__active_subscriptions__",
            None
        )

        state.pop(
            "__active_targets__",
            None
        )

        state.pop(
            "__initialized__",
            None
        )

        save_state(
            state
        )

        return {
            "new_schedules": [],
            "seat_increases": [],
        }

    client = CGVClient()

    all_new_schedules = []
    all_seat_increases = []

    active_keys = set()

    total_requests = 0
    total_special_schedules = 0

    for (
        theater_key,
        date_targets
    ) in active_targets.items():

        theater = THEATERS.get(
            theater_key
        )

        if theater is None:

            print(
                f"[경고] 알 수 없는 극장: "
                f"{theater_key}"
            )

            continue

        print()
        print(
            f"[{theater['name']}]"
        )

        # 사용자가 실제 선택한 날짜만 조회
        for (
            play_date,
            subscribed_formats
        ) in sorted(
            date_targets.items()
        ):

            # config.py에 존재하는
            # 특별관만 허용
            valid_formats = {
                special_format
                for special_format
                in subscribed_formats
                if special_format
                in theater["formats"]
            }

            if not valid_formats:
                continue

            # 실패하더라도 cleanup에서
            # 기존 상태가 삭제되지 않도록 먼저 등록
            for special_format in (
                valid_formats
            ):

                state_key = (
                    f"{theater_key}:"
                    f"{special_format}:"
                    f"{play_date}"
                )

                active_keys.add(
                    state_key
                )

            try:

                schedules = (
                    client.get_schedule(
                        theater["code"],
                        play_date,
                    )
                )

                total_requests += 1

                print(
                    f"  {play_date} "
                    f"| 전체 "
                    f"{len(schedules):3d}"
                )

                # 같은 극장/날짜 API 결과를
                # 특별관별로 나눠 처리
                for special_format in sorted(
                    valid_formats
                ):

                    special_schedules = (
                        filter_special_schedules(
                            schedules,
                            [special_format],
                        )
                    )

                    for schedule in (
                        special_schedules
                    ):

                        schedule[
                            "theater_key"
                        ] = theater_key

                        schedule[
                            "theater_name"
                        ] = theater["name"]

                    total_special_schedules += (
                        len(
                            special_schedules
                        )
                    )

                    state_key = (
                        f"{theater_key}:"
                        f"{special_format}:"
                        f"{play_date}"
                    )

                    # 이 극장/특별관/날짜를
                    # 처음 감시하는지 확인
                    first_seen = (
                        state_key
                        not in state
                    )

                    # -------------------------
                    # 취소표 감지
                    # -------------------------
                    seat_increases = (
                        track_seat_changes(
                            theater_key,
                            special_format,
                            special_schedules,
                            baseline_only=(
                                first_seen
                            ),
                        )
                    )

                    all_seat_increases.extend(
                        seat_increases
                    )

                    # -------------------------
                    # 신규 회차 감지
                    # -------------------------
                    #
                    # 날짜를 새로 선택했을 때
                    # 이미 열려 있던 회차를
                    # NEW로 오인하지 않고 baseline 처리
                    new_schedules = (
                        find_new_schedules(
                            state_key,
                            special_schedules,
                            state,
                            alert_on_first_seen=False,
                        )
                    )

                    print(
                        f"      "
                        f"{special_format:7s}"
                        f"| 회차 "
                        f"{len(special_schedules):2d}"
                        f" | NEW "
                        f"{len(new_schedules):2d}"
                    )

                    for schedule in (
                        new_schedules
                    ):

                        all_new_schedules.append(
                            schedule
                        )

            except Exception as error:

                print(
                    f"  {play_date} "
                    f"| ERROR "
                    f"{type(error).__name__}: "
                    f"{error}"
                )

        # 한 극장의 선택 날짜를 모두 조회한 뒤
        # 다음 극장으로 넘어가기 전 0.3초 대기
        if THEATER_DELAY > 0:

            time.sleep(
                THEATER_DELAY
            )

    # 더 이상 감시하지 않는
    # 날짜 / 특별관 상태 제거
    cleanup_state(
        state,
        active_keys
    )

    state.pop(
        "__active_subscriptions__",
        None
    )

    state.pop(
        "__active_targets__",
        None
    )

    state.pop(
        "__initialized__",
        None
    )

    save_state(
        state
    )

    print()
    print(
        "=" * 50
    )

    print(
        f"API 요청 완료: "
        f"{total_requests}회"
    )

    print(
        f"현재 구독 특별관 회차: "
        f"{total_special_schedules}개"
    )

    print(
        f"새로 발견된 회차: "
        f"{len(all_new_schedules)}개"
    )

    print(
        f"잔여석 증가 감지: "
        f"{len(all_seat_increases)}개"
    )

    if all_new_schedules:

        for schedule in (
            all_new_schedules
        ):

            print(
                f"[NEW]"
                f"[{schedule['format']}] "
                f"{schedule['theater_name']} - "
                f"{schedule['movie_name']}"
            )

            print(
                f"{schedule['play_date']} "
                f"| "
                f"{schedule['screen_name']} "
                f"| "
                f"{schedule['start_time']} "
                f"| 잔여석 "
                f"{schedule['remaining_seats']}"
                f"/"
                f"{schedule['total_seats']}"
            )

    else:

        print()
        print(
            "새로 열린 특별관 "
            "상영 회차가 없습니다."
        )

    return {
        "new_schedules":
            all_new_schedules,

        "seat_increases":
            all_seat_increases,
    }
    """
    현재 실제 구독자가 있는
    극장과 특별관만 감시한다.
    """

    active_subscriptions = (
        get_active_subscriptions()
    )

    state = load_state()

    # 이전 실행에서 활성화돼 있던
    # 극장/특별관 조합
    previous_subscription_ids = set(
        state.get(
            "__active_subscriptions__",
            []
        )
    )

    current_subscription_ids = set()

    for (
        theater_key,
        formats
    ) in active_subscriptions.items():

        for special_format in formats:

            current_subscription_ids.add(
                make_subscription_id(
                    theater_key,
                    special_format,
                )
            )

    # 이번에 새로 구독이 시작된 조합
    newly_added_subscription_ids = (
        current_subscription_ids
        - previous_subscription_ids
    )

    print()
    print(
        "CGV 특별관 감시 시작"
    )

    print(
        f"활성 구독 극장: "
        f"{len(active_subscriptions)}개"
    )

    print(
        f"활성 특별관 구독: "
        f"{len(current_subscription_ids)}개"
    )

    print(
        f"감시 기간: "
        f"{MONITOR_DAYS}일"
    )

    print(
        "-" * 50
    )

    # 아무도 구독하지 않으면
    # CGV 서버에 요청하지 않는다.
    if not active_subscriptions:

        print(
            "현재 활성 구독이 없습니다."
        )

        print(
            "CGV API 요청을 생략합니다."
        )

        state[
            "__active_subscriptions__"
        ] = []

        cleanup_state(
            state,
            set()
        )

        # 이전 구조의 메타데이터 제거
        state.pop(
            "__initialized__",
            None
        )

        save_state(
            state
        )

        return {
            "new_schedules": [],
            "seat_increases": [],
        }

    client = CGVClient()

    monitor_dates = (
        get_monitor_dates()
    )

    active_targets = (
        get_active_monitor_targets(
            monitor_dates
        )
    )

    all_new_schedules = []
    all_seat_increases = []

    active_keys = set()

    total_requests = 0
    total_special_schedules = 0

    for (
        theater_key,
        date_targets
    ) in active_targets.items():

        theater = THEATERS.get(
            theater_key
        )

        if theater is None:
            continue

        print()
        print(
            f"[{theater['name']}]"
        )

        for (
            play_date,
            subscribed_formats
        ) in sorted(
            date_targets.items()
        ):


            print(
                f"[경고] 알 수 없는 극장: "
                f"{theater_key}"
            )

            continue

        # config.py에 실제 등록된
        # 특별관만 감시
        valid_formats = {
            special_format
            for special_format
            in subscribed_formats
            if special_format
            in theater["formats"]
        }

        if not valid_formats:
            continue

        format_text = ", ".join(
            sorted(
                valid_formats
            )
        )

        print()
        print(
            f"[{theater['name']}] "
            f"{format_text}"
        )

        for play_date in monitor_dates:

            # 요청에 실패하더라도 기존 상태가
            # cleanup으로 사라지지 않도록
            # 먼저 active key를 등록한다.
            for special_format in valid_formats:

                state_key = (
                    f"{theater_key}:"
                    f"{special_format}:"
                    f"{play_date}"
                )

                active_keys.add(
                    state_key
                )

            try:

                schedules = (
                    client.get_schedule(
                        theater["code"],
                        play_date,
                    )
                )

                total_requests += 1

                print(
                    f"  {play_date} "
                    f"| 전체 "
                    f"{len(schedules):3d}"
                )

                # API는 극장/날짜별로 딱 한 번만 호출하고
                # 가져온 결과를 특별관별로 나눠 사용한다.
                for special_format in sorted(
                    valid_formats
                ):

                    special_schedules = (
                        filter_special_schedules(
                            schedules,
                            [special_format],
                        )
                    )
                    for schedule in special_schedules:

                        schedule[
                            "theater_key"
                        ] = theater_key

                        schedule[
                            "theater_name"
                        ] = theater["name"]

                    total_special_schedules += (
                        len(
                            special_schedules
                        )
                    )

                    state_key = (
                        f"{theater_key}:"
                        f"{special_format}:"
                        f"{play_date}"
                    )

                    subscription_id = (
                        make_subscription_id(
                            theater_key,
                            special_format,
                        )
                    )
                    is_new_subscription = (
                        subscription_id
                        in newly_added_subscription_ids
                    )

                    seat_increases = (
                        track_seat_changes(
                            theater_key,
                            special_format,
                            special_schedules,
                            baseline_only=(
                                is_new_subscription
                            ),
                        )
                    )

                    all_seat_increases.extend(
                        seat_increases
                    )

                    # 이번에 처음 구독하기 시작한
                    # 특별관이라면 현재 상태는
                    # baseline으로만 저장한다.
                    #
                    # 기존부터 구독 중인데
                    # 새로운 날짜가 감시 범위에
                    # 처음 들어온 경우에는
                    # 이미 열린 회차도 NEW 처리한다.
                    alert_on_first_seen = (
                        subscription_id
                        not in
                        newly_added_subscription_ids
                    )

                    new_schedules = (
                        find_new_schedules(
                            state_key,
                            special_schedules,
                            state,
                            alert_on_first_seen=(
                                alert_on_first_seen
                            ),
                        )
                    )

                    print(
                        f"      "
                        f"{special_format:7s}"
                        f"| 회차 "
                        f"{len(special_schedules):2d}"
                        f" | NEW "
                        f"{len(new_schedules):2d}"
                    )

                    for schedule in (
                        new_schedules
                    ):

                        schedule[
                            "theater_key"
                        ] = theater_key

                        schedule[
                            "theater_name"
                        ] = theater["name"]

                        all_new_schedules.append(
                            schedule
                        )

            except Exception as error:

                print(
                    f"  {play_date} "
                    f"| ERROR "
                    f"{type(error).__name__}: "
                    f"{error}"
                )

        time.sleep(
            THEATER_DELAY
        )   

    state[
        "__active_subscriptions__"
    ] = sorted(
        current_subscription_ids
    )

    # 예전 구조에서 사용하던
    # 메타데이터는 더 이상 필요 없다.
    state.pop(
        "__initialized__",
        None
    )

    cleanup_state(
        state,
        active_keys
    )

    save_state(
        state
    )

    print()
    print(
        "=" * 50
    )

    print(
        f"API 요청 완료: "
        f"{total_requests}회"
    )

    print(
        f"현재 구독 특별관 회차: "
        f"{total_special_schedules}개"
    )

    print(
        f"새로 발견된 회차: "
        f"{len(all_new_schedules)}개"
    )

    print(
        f"잔여석 증가 감지: "
        f"{len(all_seat_increases)}개"
    )

    if all_new_schedules:

        for schedule in (
            all_new_schedules
        ):

            print(
                f"[NEW]"
                f"[{schedule['format']}] "
                f"{schedule['theater_name']} - "
                f"{schedule['movie_name']}"
            )

            print(
                f"{schedule['play_date']} "
                f"| "
                f"{schedule['screen_name']} "
                f"| "
                f"{schedule['start_time']} "
                f"| 잔여석 "
                f"{schedule['remaining_seats']}"
                f"/"
                f"{schedule['total_seats']}"
            )

    else:

        print()
        print(
            "새로 열린 특별관 "
            "상영 회차가 없습니다."
        )

    return {
        "new_schedules":
            all_new_schedules,

        "seat_increases":
            all_seat_increases,
    }


if __name__ == "__main__":
    run_monitor()