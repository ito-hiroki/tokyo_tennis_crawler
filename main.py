import os
from datetime import datetime, timedelta
from time import sleep

import pandas as pd
import requests
import tabulate
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

# local 環境での開発時に credentials を読み込む用
local_env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(local_env_file):
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

TOKEN = os.environ["TOKEN"]
CHANNEL = os.environ["CHANNEL"]

FULLWIDTH_DIGITS = "０１２３４５６７８９"
HALFWIDTH_DIGITS = "0123456789"
FULL_HALF_DIGITS_MAP = str.maketrans(FULLWIDTH_DIGITS, HALFWIDTH_DIGITS)

target_park_list = ["1110"]
target_event_list = ["1000_1030"]
search_week_num = 2
home_url = "https://kouen.sports.metro.tokyo.lg.jp/web/"


def get_week_info(driver, target_date) -> pd.DataFrame:
    # 日程の table をパース
    week_table_html = driver.find_element(By.ID, "week-info").get_attribute("outerHTML")
    week_df = pd.read_html(week_table_html)[0]

    week_df.columns = ["Time"] + [
        (target_date + timedelta(days=n)).strftime("%Y/%m/%d") for n in range(7)
    ]

    week_df["Time"] = week_df["Time"].apply(
        lambda x: x[:-1].translate(FULL_HALF_DIGITS_MAP) + ":00"
    )
    week_df.fillna(0, inplace=True)
    week_df.set_index("Time", drop=True, inplace=True)
    return week_df


def notify_slack(week_df) -> None:
    week_string = tabulate.tabulate(week_df, headers="keys", tablefmt="psql")
    week_string = "```" + week_string + "```"

    # slack 通知
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": "Bearer " + TOKEN}
    data = {
        "channel": CHANNEL,
        "text": week_string,
    }
    requests.post(url, headers=headers, data=data)


def entrypoint(request):
    chrome_options = webdriver.ChromeOptions()

    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280x1696")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--hide-scrollbars")
    chrome_options.add_argument("--enable-logging")
    chrome_options.add_argument("--log-level=0")
    chrome_options.add_argument("--v=99")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("user-agent=" + UserAgent().random)

    chrome_options.binary_location = os.getcwd() + "/headless-chromium"
    driver = webdriver.Chrome(
        os.getcwd() + "/chromedriver", chrome_options=chrome_options
    )
    driver.implicitly_wait(10)

    for park in target_park_list:
        for event in target_event_list:
            target_date = datetime.now(ZoneInfo("Asia/Tokyo")) + timedelta(days=1)
            driver.get(home_url)
            sleep(10)

            # 検索対象の入力
            driver.find_element(By.ID, "daystart-home").send_keys(
                target_date.strftime("00%Y%m%d")
            )
            Select(driver.find_element(By.ID, "purpose-home")).select_by_value(event)
            Select(driver.find_element(By.ID, "bname-home")).select_by_value(park)
            driver.find_element(By.ID, "btn-go").click()
            sleep(10)

            for week_idx in range(search_week_num):
                week_df = get_week_info(driver, target_date)
                notify_slack(week_df)

                target_date = target_date + timedelta(days=7)
                # 次週に移動
                driver.find_element(By.ID, "next-week").click()
                sleep(10)
