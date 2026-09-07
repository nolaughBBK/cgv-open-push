import os

from dotenv import load_dotenv



load_dotenv()


DISCORD_BOT_TOKEN = os.getenv(
    "DISCORD_BOT_TOKEN"
)

DISCORD_LOG_CHANNEL_ID = int(
    os.getenv(
        "DISCORD_LOG_CHANNEL_ID",
        "0"
    )
)

DISCORD_ALERT_CHANNEL_ID = int(
    os.getenv(
        "DISCORD_ALERT_CHANNEL_ID",
        "0"
    )
)

# 앞으로 며칠까지 감시할지
MONITOR_DAYS = 14


THEATERS = {
    "YONGSAN": {
        "name": "용산아이파크몰",
        "code": "0013",
        "formats": ["IMAX", "4DX", "SCREENX"],
    },

    "YEOUIDO": {
        "name": "여의도",
        "code": "0112",
        "formats": ["4DX"],
    },

    "CENTUM": {
        "name": "센텀시티",
        "code": "0089",
        "formats": ["IMAX", "4DX"],
    },

    "SEOMYEON": {
        "name": "서면",
        "code": "0005",
        "formats": ["IMAX"],
    },

    "YEONGDEUNGPO": {
        "name": "영등포타임스퀘어",
        "code": "0059",
        "formats": ["IMAX", "SCREENX"],
    },

    "WANGSIMNI": {
        "name": "왕십리",
        "code": "0074",
        "formats": ["IMAX"],
    },

    "DAEGU": {
        "name": "대구",
        "code": "0345",
        "formats": ["IMAX", "4DX"],
    },

    "DAEGU_STADIUM": {
        "name": "대구스타디움",
        "code": "0108",
        "formats": ["4DX"],
    },
}