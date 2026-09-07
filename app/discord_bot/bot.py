import asyncio
from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import tasks

from app.config import (
    DISCORD_BOT_TOKEN,
    DISCORD_LOG_CHANNEL_ID,
    DISCORD_ALERT_CHANNEL_ID,
    THEATERS,
)

from app.cgv.monitor import run_monitor

from app.discord_bot.views import (
    NotificationSettingsView,
)

from app.storage import (
    initialize_database,
    save_open_events,
    get_user_subscriptions,
    get_subscriber_ids,
    get_seat_alert_subscriber_ids,
    get_user_party_size,
)


intents = discord.Intents.default()

client = discord.Client(
    intents=intents
)

tree = app_commands.CommandTree(
    client
)


commands_synced = False

async def get_channel(
    channel_id: int
):

    channel = client.get_channel(
        channel_id
    )

    if channel is None:

        channel = await client.fetch_channel(
            channel_id
        )

    return channel


async def send_log(
    message: str
):

    try:

        channel = await get_channel(
            DISCORD_LOG_CHANNEL_ID
        )

        await channel.send(
            message
        )

    except Exception as error:

        print(
            f"Discord LOG 전송 실패: "
            f"{error}"
        )


def format_date(
    play_date: str
):

    if len(play_date) != 8:
        return play_date

    return (
        f"{play_date[:4]}-"
        f"{play_date[4:6]}-"
        f"{play_date[6:8]}"
    )


def format_time(
    start_time: str
):

    if len(start_time) < 4:
        return start_time

    return (
        f"{start_time[:-2]}:"
        f"{start_time[-2:]}"
    )


@tree.command(
    name="알림설정",
    description=(
        "CGV 특별관 예매 오픈 알림을 설정합니다."
    )
)
async def notification_settings(
    interaction: discord.Interaction
):

    existing = get_user_subscriptions(
        interaction.user.id
    )

    party_size = (
        get_user_party_size(
            interaction.user.id
        )
    )

    if existing:

        current_names = []

        for (
            theater_key,
            special_format
        ) in sorted(existing):

            theater = THEATERS.get(
                theater_key
            )

            if theater:

                current_names.append(
                    f"• {theater['name']} "
                    f"{special_format}"
                )

        current_text = "\n".join(
            current_names
        )

        message = (
            "🎬 **CGV 특별관 알림 설정**\n\n"
            "현재 설정:\n"
            f"{current_text}"
            f"\n\n👥 취소표 예매 인원: "
            f"**{party_size}명**"
            "\n\n아래 메뉴에서 원하는 특별관을 "
            "다시 선택하면 설정이 저장됩니다."
        )

    else:

        message = (
            "🎬 **CGV 특별관 알림 설정**\n\n"
            "현재 설정된 알림이 없습니다."
            f"\n\n👥 취소표 예매 인원: "
            f"**{party_size}명**"
            "\n\n아래 메뉴에서 알림을 받을 "
            "극장과 특별관을 선택하세요."
        )

    view = NotificationSettingsView(
        interaction.user.id
    )

    await interaction.response.send_message(
        message,
        view=view,
        ephemeral=True,
    )


async def send_new_schedules(
    schedules
):

    channel = await get_channel(
        DISCORD_ALERT_CHANNEL_ID
    )

    grouped = defaultdict(list)

    for schedule in schedules:

        key = (
            schedule["theater_key"],
            schedule["theater_name"],
            schedule["play_date"],
            schedule["format"],
        )

        grouped[key].append(
            schedule
        )

    for (
        theater_key,
        theater_name,
        play_date,
        special_format
    ), items in grouped.items():

        subscriber_ids = (
            get_subscriber_ids(
                theater_key,
                special_format,
                play_date,
            )
        )

        if not subscriber_ids:

            print(
                f"구독자 없음: "
                f"{theater_name} "
                f"{special_format}"
            )

            continue

        mentions = " ".join(
            f"<@{user_id}>"
            for user_id
            in subscriber_ids
        )

        items.sort(
            key=lambda item: (
                item["start_time"]
            )
        )

        header = (
            f"{mentions}\n"
            f"🎬 **CGV 예매 오픈 감지**\n"
            f"📍 **{theater_name}**\n"
            f"🎥 **{special_format}**\n"
            f"📅 {format_date(play_date)}\n\n"
        )

        message = header

        for item in items:

            line = (
                f"• **"
                f"{format_time(item['start_time'])}"
                f"** "
                f"{item['movie_name']}\n"
                f"  └ {item['screen_name']} | "
                f"잔여석 "
                f"{item['remaining_seats']}"
                f"/"
                f"{item['total_seats']}\n"
            )

            if (
                len(message)
                + len(line)
                > 1850
            ):

                await channel.send(
                    message,
                    allowed_mentions=(
                        discord.AllowedMentions(
                            users=True,
                            roles=False,
                            everyone=False,
                        )
                    ),
                )

                message = (
                    f"{mentions}\n"
                    f"🎬 **CGV 예매 오픈 감지 "
                    f"(계속)**\n"
                    f"📍 **{theater_name}**\n"
                    f"🎥 **{special_format}**\n"
                    f"📅 "
                    f"{format_date(play_date)}\n\n"
                )

            message += line

    

        await channel.send(
            message,
            allowed_mentions=(
                discord.AllowedMentions(
                    users=True,
                    roles=False,
                    everyone=False,
                )
            ),
        )

async def send_seat_increases(
    seat_increases
):

    channel = await get_channel(
        DISCORD_ALERT_CHANNEL_ID
    )

    for change in seat_increases:

        subscriber_ids = (
            get_seat_alert_subscriber_ids(
                change["theater_key"],
                change["format"],
                change["play_date"],
                change["seat_increase"],
            )
        )

        if not subscriber_ids:
            continue

        mentions = " ".join(
            f"<@{user_id}>"
            for user_id
            in subscriber_ids
        )

        message = (
            f"{mentions}\n"
            f"🎟️ **취소표 감지**\n"
            f"📍 **"
            f"{change['theater_name']}"
            f"**\n"
            f"🎥 **"
            f"{change['format']}"
            f"**\n"
            f"📅 "
            f"{format_date(change['play_date'])}\n"
            f"🕒 **"
            f"{format_time(change['start_time'])}"
            f"** "
            f"{change['movie_name']}\n\n"
            f"잔여석 "
            f"**"
            f"{change['previous_remaining_seats']}"
            f" → "
            f"{change['current_remaining_seats']}"
            f"**\n"
            f"▲ **"
            f"{change['seat_increase']}"
            f"석 증가**"
        )

        await channel.send(
            message,
            allowed_mentions=(
                discord.AllowedMentions(
                    users=True,
                    roles=False,
                    everyone=False,
                )
            ),
        )

@tasks.loop(
    minutes=1
    # seconds=10
)
async def monitor_loop():

    try:

        print(
            "CGV 모니터링 실행..."
        )

        monitor_result = (
            await asyncio.to_thread(
                run_monitor
            )
        )

        new_schedules = (
            monitor_result[
                "new_schedules"
            ]
        )

        seat_increases = (
            monitor_result[
                "seat_increases"
            ]
        )

        if new_schedules:

            saved_count = (
                save_open_events(
                    new_schedules
                )
            )

            print(
                f"신규 회차 DB 저장: "
                f"{saved_count}개"
            )

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


        if seat_increases:

            print(
                f"취소표 변화 감지: "
                f"{len(seat_increases)}개"
            )

            await send_seat_increases(
                seat_increases
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

    global commands_synced

    print(
        f"Discord 로그인 성공: "
        f"{client.user}"
    )

    if not commands_synced:

        try:

            synced = await tree.sync()

            print(
                f"Slash 명령어 동기화 완료: "
                f"{len(synced)}개"
            )

            commands_synced = True

        except Exception as error:

            print(
                f"Slash 명령어 동기화 실패: "
                f"{error}"
            )

    if not monitor_loop.is_running():

        monitor_loop.start()

        await send_log(
            "cgv-open-push 실행 시작\n"
            "CGV 특별관 감시를 시작합니다."
        )


def run_bot():

    initialize_database()

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