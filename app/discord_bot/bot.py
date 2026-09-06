import asyncio
from collections import defaultdict

import discord
from discord.ext import tasks

from app.config import (
    DISCORD_BOT_TOKEN,
    DISCORD_LOG_CHANNEL_ID,
    DISCORD_ALERT_CHANNEL_ID,
)
from app.cgv.monitor import run_monitor


intents = discord.Intents.default()

client = discord.Client(
    intents=intents
)


async def get_channel(channel_id: int):
    """
    Discord 채널을 가져온다.
    """

    channel = client.get_channel(
        channel_id
    )

    if channel is None:
        channel = await client.fetch_channel(
            channel_id
        )

    return channel


async def send_log(message: str):
    """
    bot-log 채널에 로그 메시지를 보낸다.
    """

    try:
        channel = await get_channel(
            DISCORD_LOG_CHANNEL_ID
        )

        await channel.send(message)

    except Exception as error:
        print(
            f"Discord LOG 전송 실패: "
            f"{error}"
        )


def format_date(play_date: str):
    """
    20260907 -> 2026-09-07
    """

    if len(play_date) != 8:
        return play_date

    return (
        f"{play_date[:4]}-"
        f"{play_date[4:6]}-"
        f"{play_date[6:8]}"
    )


def format_time(start_time: str):
    """
    1430 -> 14:30
    2500 -> 25:00
    """

    if len(start_time) < 4:
        return start_time

    return (
        f"{start_time[:-2]}:"
        f"{start_time[-2:]}"
    )


async def send_new_schedules(
    schedules
):
    """
    새로 발견된 상영 회차를
    극장 / 날짜 / 특별관별로 묶어서 전송한다.
    """

    channel = await get_channel(
        DISCORD_ALERT_CHANNEL_ID
    )

    grouped = defaultdict(list)

    for schedule in schedules:
        key = (
            schedule["theater_name"],
            schedule["play_date"],
            schedule["format"],
        )

        grouped[key].append(
            schedule
        )

    for (
        theater_name,
        play_date,
        special_format
    ), items in grouped.items():

        items.sort(
            key=lambda item: (
                item["start_time"]
            )
        )

        message = (
            f"🎬 **CGV 예매 오픈 감지**\n"
            f"📍 **{theater_name}**\n"
            f"🎥 **{special_format}**\n"
            f"📅 {format_date(play_date)}\n\n"
        )

        for item in items:

            line = (
                f"• **{format_time(item['start_time'])}** "
                f"{item['movie_name']}\n"
                f"  └ {item['screen_name']} | "
                f"잔여석 "
                f"{item['remaining_seats']}"
                f"/"
                f"{item['total_seats']}\n"
            )

            # Discord 메시지 길이 제한 대비
            if len(message) + len(line) > 1900:
                await channel.send(
                    message
                )

                message = (
                    f"🎬 **CGV 예매 오픈 감지 "
                    f"(계속)**\n"
                    f"📍 **{theater_name}**\n"
                    f"🎥 **{special_format}**\n"
                    f"📅 {format_date(play_date)}\n\n"
                )

            message += line

        message += (
            "\n🔗 https://cgv.co.kr/cnm/movieBook"
        )

        await channel.send(
            message
        )


@tasks.loop(
    minutes=5
)
async def monitor_loop():
    """
    5분마다 CGV 특별관을 확인한다.
    """

    try:
        print(
            "\nCGV 모니터링 실행..."
        )

        # run_monitor()는 동기 함수이므로
        # Discord 이벤트 루프를 막지 않도록
        # 별도 스레드에서 실행
        new_schedules = (
            await asyncio.to_thread(
                run_monitor
            )
        )

        if new_schedules:
            print(
                f"Discord 알림 대상: "
                f"{len(new_schedules)}개"
            )

            await send_new_schedules(
                new_schedules
            )

        else:
            print(
                "새로운 회차 없음"
            )

    except Exception as error:
        error_message = (
            f"CGV 모니터링 오류\n"
            f"{type(error).__name__}: "
            f"{error}"
        )

        print(
            error_message
        )

        await send_log(
            error_message
        )


@monitor_loop.before_loop
async def before_monitor_loop():
    await client.wait_until_ready()


@client.event
async def on_ready():

    print(
        f"Discord 로그인 성공: "
        f"{client.user}"
    )

    # Discord 재접속 시
    # monitor_loop가 중복 생성되지 않도록 방지
    if not monitor_loop.is_running():

        monitor_loop.start()

        await send_log(
            "cgv-open-push 실행 시작\n"
            "CGV 특별관 감시를 시작합니다."
        )


def run_bot():

    if not DISCORD_BOT_TOKEN:
        raise RuntimeError(
            "DISCORD_BOT_TOKEN이 "
            "설정되지 않았습니다."
        )

    if not DISCORD_LOG_CHANNEL_ID:
        raise RuntimeError(
            "DISCORD_LOG_CHANNEL_ID가 "
            "설정되지 않았습니다."
        )

    if not DISCORD_ALERT_CHANNEL_ID:
        raise RuntimeError(
            "DISCORD_ALERT_CHANNEL_ID가 "
            "설정되지 않았습니다."
        )

    client.run(
        DISCORD_BOT_TOKEN
    )


if __name__ == "__main__":
    run_bot()