import discord

from datetime import datetime, timedelta
from app.config import (
    THEATERS,
    MONITOR_DAYS,
)
from app.storage import (
    get_user_subscriptions,
    replace_user_subscriptions,
    clear_user_subscriptions,
    get_user_party_size,
    set_user_party_size,
    get_user_dates,
    replace_user_dates,
)


class NotificationSelect(
    discord.ui.Select
):

    def __init__(
        self,
        owner_id: int
    ):

        existing = get_user_subscriptions(
            owner_id
        )

        options = []

        for (
            theater_key,
            theater
        ) in THEATERS.items():

            for special_format in theater["formats"]:

                options.append(
                    discord.SelectOption(
                        label=(
                            f"{theater['name']} "
                            f"{special_format}"
                        ),
                        value=(
                            f"{theater_key}|"
                            f"{special_format}"
                        ),
                        default=(
                            (
                                theater_key,
                                special_format
                            )
                            in existing
                        )
                    )
                )

        super().__init__(
            placeholder=(
                "알림 받을 극장과 특별관을 선택하세요"
            ),
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        selections = []

        for value in self.values:

            theater_key, special_format = (
                value.split(
                    "|",
                    1
                )
            )

            selections.append(
                (
                    theater_key,
                    special_format
                )
            )

        saved_count = (
            replace_user_subscriptions(
                interaction.user.id,
                selections
            )
        )

        selected_names = []

        for (
            theater_key,
            special_format
        ) in selections:

            theater_name = (
                THEATERS[
                    theater_key
                ]["name"]
            )

            selected_names.append(
                f"• {theater_name} "
                f"{special_format}"
            )

        message = (
            f"✅ **알림 설정 저장 완료**\n\n"
            f"총 {saved_count}개 특별관을 "
            f"구독합니다.\n\n"
            + "\n".join(
                selected_names
            )
            + (
                f"\n\n👥 취소표 예매 인원: "
                f"**{party_size}명**"
            )
        )

        await interaction.response.edit_message(
            content=message,
            view=self.view,
        )

class DateSelect(
    discord.ui.Select
):

    def __init__(
        self,
        owner_id: int
    ):

        saved_dates = get_user_dates(
            owner_id
        )

        today = datetime.now()

        monitor_dates = [
            (
                today
                + timedelta(days=day)
            ).strftime("%Y%m%d")
            for day in range(
                MONITOR_DAYS
            )
        ]

        # 날짜를 아직 설정한 적이 없다면
        # 전체 날짜가 기본 선택
        if not saved_dates:
            selected_dates = set(
                monitor_dates
            )
        else:
            selected_dates = saved_dates

        weekday_names = [
            "월",
            "화",
            "수",
            "목",
            "금",
            "토",
            "일",
        ]

        options = []

        for play_date in monitor_dates:

            date_object = datetime.strptime(
                play_date,
                "%Y%m%d"
            )

            weekday = weekday_names[
                date_object.weekday()
            ]

            options.append(
                discord.SelectOption(
                    label=(
                        f"{date_object.month}/"
                        f"{date_object.day} "
                        f"({weekday})"
                    ),
                    value=play_date,
                    description=(
                        date_object.strftime(
                            "%Y-%m-%d"
                        )
                    ),
                    default=(
                        play_date
                        in selected_dates
                    ),
                )
            )

        super().__init__(
            placeholder=(
                "알림 받을 날짜를 선택하세요"
            ),
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        selected_dates = sorted(
            self.values
        )

        replace_user_dates(
            interaction.user.id,
            selected_dates,
        )

        readable_dates = []

        for play_date in selected_dates:

            date_object = datetime.strptime(
                play_date,
                "%Y%m%d"
            )

            readable_dates.append(
                date_object.strftime(
                    "%m/%d"
                )
            )

        await interaction.response.send_message(
            (
                f"📅 알림 날짜를 "
                f"**{len(selected_dates)}일** "
                f"선택했습니다.\n"
                f"{', '.join(readable_dates)}"
            ),
            ephemeral=True,
        )

class PartySizeSelect(
    discord.ui.Select
):

    def __init__(
        self,
        owner_id: int
    ):

        current_party_size = (
            get_user_party_size(
                owner_id
            )
        )

        options = []

        for party_size in range(
            1,
            5
        ):

            options.append(
                discord.SelectOption(
                    label=(
                        f"{party_size}명"
                    ),
                    value=str(
                        party_size
                    ),
                    description=(
                        f"한 번에 "
                        f"{party_size}석 이상 "
                        f"늘어나면 알림"
                    ),
                    default=(
                        party_size
                        == current_party_size
                    ),
                )
            )

        super().__init__(
            placeholder=(
                "취소표 예매 인원을 선택하세요"
            ),
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        party_size = int(
            self.values[0]
        )

        set_user_party_size(
            interaction.user.id,
            party_size,
        )

        await interaction.response.send_message(
            (
                f"👥 취소표 알림 인원을 "
                f"**{party_size}명**으로 "
                f"설정했습니다.\n"
                f"한 번의 조회에서 잔여석이 "
                f"{party_size}석 이상 늘어나면 "
                f"알림을 보냅니다."
            ),
            ephemeral=True,
        )
        
class NotificationSettingsView(
    discord.ui.View
):

    def __init__(
        self,
        owner_id: int
    ):

        super().__init__(
            timeout=300
        )

        self.owner_id = owner_id

        self.add_item(
            NotificationSelect(
                owner_id
            )
        )
        self.add_item(
            DateSelect(
                owner_id
            )
        )
        self.add_item(
            PartySizeSelect(
                owner_id
            )
        )
    async def interaction_check(
        self,
        interaction: discord.Interaction
    ):

        if (
            interaction.user.id
            != self.owner_id
        ):

            await interaction.response.send_message(
                "다른 사용자의 알림 설정은 "
                "변경할 수 없습니다.",
                ephemeral=True,
            )

            return False

        return True

    @discord.ui.button(
        label="전체 알림 해제",
        style=discord.ButtonStyle.danger,
        emoji="🔕",
    )
    async def clear_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        clear_user_subscriptions(
            interaction.user.id
        )

        await interaction.response.edit_message(
            content=(
                "🔕 모든 CGV 특별관 알림을 "
                "해제했습니다.\n\n"
                "다시 설정하려면 "
                "`/알림설정`을 실행하세요."
            ),
            view=None,
        )

        self.stop()