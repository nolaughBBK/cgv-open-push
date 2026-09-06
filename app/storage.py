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
    신규 회차 감지 이력을 저장할 테이블을 만든다.
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

        connection.commit()


def save_open_events(schedules):
    """
    NEW로 감지된 회차들을 DB에 저장한다.

    schedule_id가 이미 저장된 회차라면
    중복 저장하지 않는다.
    """

    if not schedules:
        return 0

    detected_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    inserted_count = 0

    with get_connection() as connection:

        for schedule in schedules:

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
                    schedule["id"],
                )
            )

            inserted_count += (
                cursor.rowcount
            )

        connection.commit()

    return inserted_count


def get_recent_events(limit=20):
    """
    최근 감지된 오픈 이력을 조회한다.
    """

    initialize_database()

    with get_connection() as connection:

        connection.row_factory = (
            sqlite3.Row
        )

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
        print(
            event
        )