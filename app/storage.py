import sqlite3
from datetime import datetime
from pathlib import Path


DB_PATH = Path("data/cgv_history.db")


def get_connection():
    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    return sqlite3.connect(
        DB_PATH
    )


def initialize_database():
    """
    CGV 오픈 이력과
    Discord 사용자 알림 설정 테이블을 만든다.
    """

    with get_connection() as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS open_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                detected_at TEXT NOT NULL,

                theater_key TEXT NOT NULL,
                theater_name TEXT NOT NULL,

                special_format TEXT NOT NULL,

                play_date TEXT NOT NULL,
                movie_name TEXT NOT NULL,
                screen_name TEXT NOT NULL,
                start_time TEXT NOT NULL,

                remaining_seats INTEGER,
                total_seats INTEGER,

                schedule_id TEXT NOT NULL UNIQUE
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER NOT NULL,
                theater_key TEXT NOT NULL,
                special_format TEXT NOT NULL,
                created_at TEXT NOT NULL,

                PRIMARY KEY (
                    user_id,
                    theater_key,
                    special_format
                )
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                party_size INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS seat_snapshots (
                theater_key TEXT NOT NULL,
                special_format TEXT NOT NULL,
                schedule_id TEXT NOT NULL,

                remaining_seats INTEGER NOT NULL,
                updated_at TEXT NOT NULL,

                PRIMARY KEY (
                    theater_key,
                    special_format,
                    schedule_id
                )
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS subscription_dates (
                user_id INTEGER NOT NULL,
                play_date TEXT NOT NULL,
                updated_at TEXT NOT NULL,

                PRIMARY KEY (
                    user_id,
                    play_date
                )
            )
            """
        )

        connection.commit()


def save_open_events(schedules):
    """
    NEW로 감지된 CGV 회차를 저장한다.
    """

    if not schedules:
        return 0

    initialize_database()

    detected_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    inserted_count = 0

    with get_connection() as connection:

        for schedule in schedules:

            # 서로 다른 극장의 회차 ID가
            # 우연히 겹치는 상황까지 방지
            database_schedule_id = (
                f"{schedule['theater_key']}:"
                f"{schedule['id']}"
            )

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO open_events (
                    detected_at,
                    theater_key,
                    theater_name,
                    special_format,
                    play_date,
                    movie_name,
                    screen_name,
                    start_time,
                    remaining_seats,
                    total_seats,
                    schedule_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    detected_at,
                    schedule["theater_key"],
                    schedule["theater_name"],
                    schedule["format"],
                    schedule["play_date"],
                    schedule["movie_name"],
                    schedule["screen_name"],
                    schedule["start_time"],
                    schedule["remaining_seats"],
                    schedule["total_seats"],
                    database_schedule_id,
                )
            )

            inserted_count += cursor.rowcount

        connection.commit()

    return inserted_count


def get_recent_events(limit=20):
    """
    최근 CGV 오픈 감지 이력을 조회한다.
    """

    initialize_database()

    with get_connection() as connection:

        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT *
            FROM open_events
            ORDER BY detected_at DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_user_subscriptions(user_id: int):
    """
    특정 Discord 사용자가 선택한
    극장/특별관 조합을 가져온다.
    """

    initialize_database()

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT
                theater_key,
                special_format
            FROM subscriptions
            WHERE user_id = ?
            ORDER BY theater_key, special_format
            """,
            (user_id,)
        ).fetchall()

    return {
        (row[0], row[1])
        for row in rows
    }

def get_user_dates(
    user_id: int
):
    """
    사용자가 직접 선택한 날짜를 가져온다.

    빈 set이면 날짜를 따로 설정하지 않은 상태이며
    모니터에서는 전체 감시 기간으로 취급한다.
    """

    initialize_database()

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT play_date
            FROM subscription_dates
            WHERE user_id = ?
            ORDER BY play_date
            """,
            (user_id,)
        ).fetchall()

    return {
        row[0]
        for row in rows
    }


def replace_user_dates(
    user_id: int,
    play_dates
):
    """
    사용자의 날짜 설정을 교체한다.
    """

    initialize_database()

    updated_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    with get_connection() as connection:

        connection.execute(
            """
            DELETE FROM subscription_dates
            WHERE user_id = ?
            """,
            (user_id,)
        )

        rows = [
            (
                user_id,
                play_date,
                updated_at,
            )
            for play_date in play_dates
        ]

        if rows:

            connection.executemany(
                """
                INSERT INTO subscription_dates (
                    user_id,
                    play_date,
                    updated_at
                )
                VALUES (?, ?, ?)
                """,
                rows
            )

        connection.commit()

    return len(rows)

def replace_user_subscriptions(
    user_id: int,
    subscriptions
):
    """
    사용자의 기존 설정을 지우고
    새 선택값으로 교체한다.
    """

    initialize_database()

    created_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    with get_connection() as connection:

        connection.execute(
            """
            DELETE FROM subscriptions
            WHERE user_id = ?
            """,
            (user_id,)
        )

        rows = [
            (
                user_id,
                theater_key,
                special_format,
                created_at,
            )
            for theater_key, special_format
            in subscriptions
        ]

        if rows:
            connection.executemany(
                """
                INSERT INTO subscriptions (
                    user_id,
                    theater_key,
                    special_format,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                rows
            )

        connection.commit()

    return len(rows)

def get_active_monitor_targets(
    default_dates
):
    """
    실제 구독자들의 특별관 + 날짜 설정을 합쳐
    필요한 CGV 조회 대상만 만든다.

    반환 예:
    {
        "CENTUM": {
            "20260910": {"IMAX"},
            "20260911": {"IMAX"},
        },
        "DAEGU": {
            "20260910": {"IMAX", "4DX"},
        }
    }

    날짜를 한 번도 설정하지 않은 사용자는
    default_dates 전체를 구독한 것으로 처리한다.
    """

    initialize_database()

    default_dates = set(
        default_dates
    )

    with get_connection() as connection:

        subscriptions = connection.execute(
            """
            SELECT
                user_id,
                theater_key,
                special_format
            FROM subscriptions
            """
        ).fetchall()

        date_rows = connection.execute(
            """
            SELECT
                user_id,
                play_date
            FROM subscription_dates
            """
        ).fetchall()

    user_dates = {}

    for user_id, play_date in date_rows:

        user_dates.setdefault(
            int(user_id),
            set()
        ).add(
            play_date
        )

    targets = {}

    for (
        user_id,
        theater_key,
        special_format
    ) in subscriptions:

        selected_dates = user_dates.get(
            int(user_id)
        )

        # 기존 사용자처럼 날짜 설정이 없으면
        # 전체 감시 기간
        if not selected_dates:
            selected_dates = default_dates

        for play_date in selected_dates:

            if play_date not in default_dates:
                continue

            targets.setdefault(
                theater_key,
                {}
            ).setdefault(
                play_date,
                set()
            ).add(
                special_format
            )

    return targets

def clear_user_subscriptions(user_id: int):
    """
    특정 사용자의 알림을 전부 해제한다.
    """

    initialize_database()

    with get_connection() as connection:

        cursor = connection.execute(
            """
            DELETE FROM subscriptions
            WHERE user_id = ?
            """,
            (user_id,)
        )

        connection.commit()

    return cursor.rowcount

def get_active_subscriptions():
    """
    현재 한 명이라도 구독하고 있는
    극장/특별관 조합을 가져온다.

    반환 예시:
    {
        "YONGSAN": {"IMAX", "4DX"},
        "DAEGU": {"IMAX"},
    }
    """

    initialize_database()

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT DISTINCT
                theater_key,
                special_format
            FROM subscriptions
            ORDER BY theater_key, special_format
            """
        ).fetchall()

    active = {}

    for theater_key, special_format in rows:

        if theater_key not in active:
            active[theater_key] = set()

        active[theater_key].add(
            special_format
        )

    return active


def get_subscriber_ids(
    theater_key: str,
    special_format: str,
    play_date: str,
):
    """
    해당 극장/특별관/날짜를
    구독하고 있는 사용자만 가져온다.

    날짜 설정이 없는 사용자는
    모든 날짜를 구독한 것으로 처리한다.
    """

    initialize_database()

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT s.user_id

            FROM subscriptions AS s

            WHERE s.theater_key = ?
              AND s.special_format = ?

              AND (
                    NOT EXISTS (
                        SELECT 1
                        FROM subscription_dates AS d
                        WHERE d.user_id = s.user_id
                    )

                    OR EXISTS (
                        SELECT 1
                        FROM subscription_dates AS d
                        WHERE d.user_id = s.user_id
                          AND d.play_date = ?
                    )
                  )

            ORDER BY s.user_id
            """,
            (
                theater_key,
                special_format,
                play_date,
            )
        ).fetchall()

    return [
        int(row[0])
        for row in rows
    ]

def get_user_party_size(
    user_id: int
):
    """
    사용자가 설정한 예매 인원을 가져온다.
    기본값은 1명.
    """

    initialize_database()

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT party_size
            FROM user_settings
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()

    if row is None:
        return 1

    return int(row[0])


def set_user_party_size(
    user_id: int,
    party_size: int
):
    """
    사용자의 취소표 감지 인원을 저장한다.
    """

    if party_size not in (
        1,
        2,
        3,
        4,
    ):
        raise ValueError(
            "예매 인원은 1~4명만 가능합니다."
        )

    initialize_database()

    updated_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    with get_connection() as connection:

        connection.execute(
            """
            INSERT INTO user_settings (
                user_id,
                party_size,
                updated_at
            )
            VALUES (?, ?, ?)

            ON CONFLICT(user_id)
            DO UPDATE SET
                party_size = excluded.party_size,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                party_size,
                updated_at,
            )
        )

        connection.commit()


def track_seat_changes(
    theater_key: str,
    special_format: str,
    schedules,
    baseline_only=False,
):
    """
    회차별 잔여석을 직전 조회와 비교한다.

    잔여석이 증가한 경우에만 반환한다.

    baseline_only=True이면
    현재 좌석 수만 저장하고 변화는 감지하지 않는다.
    """

    initialize_database()

    seat_increases = []

    updated_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    with get_connection() as connection:

        for schedule in schedules:

            current_remaining = (
                schedule.get(
                    "remaining_seats"
                )
            )

            if current_remaining is None:
                continue

            current_remaining = int(
                current_remaining
            )

            schedule_id = schedule["id"]

            row = connection.execute(
                """
                SELECT remaining_seats
                FROM seat_snapshots
                WHERE theater_key = ?
                  AND special_format = ?
                  AND schedule_id = ?
                """,
                (
                    theater_key,
                    special_format,
                    schedule_id,
                )
            ).fetchone()

            if (
                row is not None
                and not baseline_only
            ):

                previous_remaining = int(
                    row[0]
                )

                increase = (
                    current_remaining
                    - previous_remaining
                )

                if increase > 0:

                    change = dict(
                        schedule
                    )

                    change[
                        "previous_remaining_seats"
                    ] = previous_remaining

                    change[
                        "current_remaining_seats"
                    ] = current_remaining

                    change[
                        "seat_increase"
                    ] = increase

                    seat_increases.append(
                        change
                    )

            connection.execute(
                """
                INSERT INTO seat_snapshots (
                    theater_key,
                    special_format,
                    schedule_id,
                    remaining_seats,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)

                ON CONFLICT(
                    theater_key,
                    special_format,
                    schedule_id
                )
                DO UPDATE SET
                    remaining_seats =
                        excluded.remaining_seats,
                    updated_at =
                        excluded.updated_at
                """,
                (
                    theater_key,
                    special_format,
                    schedule_id,
                    current_remaining,
                    updated_at,
                )
            )

        connection.commit()

    return seat_increases


def get_seat_alert_subscriber_ids(
    theater_key: str,
    special_format: str,
    play_date: str,
    seat_increase: int,
):
    """
    해당 날짜를 구독하고,
    취소표 증가량 조건까지 만족한 사용자만 조회한다.
    """

    initialize_database()

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT s.user_id

            FROM subscriptions AS s

            LEFT JOIN user_settings AS u
                ON s.user_id = u.user_id

            WHERE s.theater_key = ?
              AND s.special_format = ?

              AND COALESCE(
                    u.party_size,
                    1
                  ) <= ?

              AND (
                    NOT EXISTS (
                        SELECT 1
                        FROM subscription_dates AS d
                        WHERE d.user_id = s.user_id
                    )

                    OR EXISTS (
                        SELECT 1
                        FROM subscription_dates AS d
                        WHERE d.user_id = s.user_id
                          AND d.play_date = ?
                    )
                  )
            """,
            (
                theater_key,
                special_format,
                seat_increase,
                play_date,
            )
        ).fetchall()

    return [
        int(row[0])
        for row in rows
    ]

if __name__ == "__main__":

    initialize_database()

    print(
        f"DB 초기화 완료: "
        f"{DB_PATH}"
    )

    events = get_recent_events()

    print(
        f"저장된 최근 이벤트: "
        f"{len(events)}개"
    )

    for event in events:
        print(event)