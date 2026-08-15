import requests
from bs4 import BeautifulSoup
import time
import random
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo


# ============================================================
# 設定
# ============================================================

URL = "https://mensa.jp/exam/"

# ntfy通知先
NOTIFY_URL = "https://ntfy.sh/akira-mensa-watch"

# 状態保存ファイル
STATE_FILE = "mensa_state.json"

# ログファイル
LOG_FILE = "mensa_watch.log"

# 監視間隔
MIN_WAIT = 40
MAX_WAIT = 90

# 1回のGitHub Actionsで監視する最大時間（秒）
MAX_RUNTIME = 240

# 10月監視対象
OCTOBER_TARGET_WARDS = [
    "大阪市北区",
    "大阪市福島区",
]

# 11月以降
FUTURE_MONTH = 11

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# ============================================================
# ログ
# ============================================================

def log(message):

    text = (
        f"{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d %H:%M:%S')} "
        f"{message}"
    )

    print(text)

    with open(
        LOG_FILE,
        "a",
        encoding="utf-8"
    ) as f:
        f.write(text + "\n")


# ============================================================
# 通知
# ============================================================

def notify(title, message):

    try:

        body = (
            f"{title}\n\n"
            f"{message}"
        )

        headers = {
            "Priority": "high",
            "Tags": "warning"
        }

        r = requests.post(
            NOTIFY_URL,
            data=body.encode("utf-8"),
            headers=headers,
            timeout=10
        )

        if r.ok:

            log(
                "通知送信成功"
            )

        else:

            log(
                f"通知送信失敗 HTTP {r.status_code}"
            )

    except Exception as e:

        log(
            f"通知エラー: {e}"
        )


# ============================================================
# 状態読み込み
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):

        return {
            "october": {},
            "future": {}
        }

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            state = json.load(f)

        return state

    except Exception as e:

        log(
            f"状態ファイル読み込みエラー: {e}"
        )

        return {
            "october": {},
            "future": {}
        }


# ============================================================
# 状態保存
# ============================================================

def save_state(state):

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# 試験ページ取得
# ============================================================

def get_page():

    r = requests.get(
        URL,
        headers=HEADERS,
        timeout=15
    )

    r.raise_for_status()

    r.encoding = r.apparent_encoding

    return r.text


# ============================================================
# 試験情報解析
# ============================================================

def parse_exams(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    exams = []

    lists = soup.select(
        "ul.list"
    )

    for item in lists:

        pref = item.select_one(
            "li.pref"
        )

        date_li = item.select_one(
            "li.date"
        )

        link_li = item.select_one(
            "li.link"
        )

        if not pref or not date_li or not link_li:
            continue

        # ----------------------------------------------------
        # 都道府県
        # ----------------------------------------------------

        pref_text = pref.get_text(
            " ",
            strip=True
        )

        # ----------------------------------------------------
        # 日時・場所
        # ----------------------------------------------------

        date_text = date_li.get_text(
            " ",
            strip=True
        )

        date_match = re.search(
            r"日時\s*[：:]\s*"
            r"([0-9]{4}/[0-9]{1,2}/[0-9]{1,2}"
            r"\([^)]*\)\s*"
            r"[0-9]{1,2}:[0-9]{2}"
            r"~"
            r"[0-9]{1,2}:[0-9]{2})",
            date_text
        )

        if not date_match:
            continue

        datetime_text = date_match.group(1)

        # ----------------------------------------------------
        # 日付
        # ----------------------------------------------------

        date_match2 = re.search(
            r"([0-9]{4})/([0-9]{1,2})/([0-9]{1,2})",
            datetime_text
        )

        if not date_match2:
            continue

        year = int(
            date_match2.group(1)
        )

        month = int(
            date_match2.group(2)
        )

        day = int(
            date_match2.group(3)
        )

        date_short = (
            f"{month}/{day}"
        )

        # ----------------------------------------------------
        # 場所
        # ----------------------------------------------------

        place_match = re.search(
            r"場所\s*[：:]\s*(.+?)(?=このテストには|$)",
            date_text
        )

        if not place_match:
            continue

        place = place_match.group(1).strip()

        # ----------------------------------------------------
        # ボタン画像から状態判定
        # ----------------------------------------------------

        img = link_li.select_one(
            "img"
        )

        if not img:
            continue

        src = img.get(
            "src",
            ""
        )

        alt = img.get(
            "alt",
            ""
        )

        if "entry_out" in src:

            status = "open"

        elif "entry_quota" in src:

            status = "full"

        elif "entry_expire" in src:

            status = "expired"

        else:

            status = "unknown"

        # ----------------------------------------------------
        # 申し込みURL
        # ----------------------------------------------------

        a = link_li.select_one(
            "a"
        )

        href = ""

        if a:

            href = a.get(
                "href",
                ""
            )

            if href.startswith("/"):

                href = (
                    "https://mensa.jp"
                    + href
                )

            elif href.startswith("exam/"):

                href = (
                    "https://mensa.jp/"
                    + href
                )

        # ----------------------------------------------------
        # 一意なID
        # ----------------------------------------------------

        key = (
            f"{year}-{month:02d}-{day:02d}"
            f"|{datetime_text}"
            f"|{place}"
        )

        exam = {
            "key": key,
            "year": year,
            "month": month,
            "day": day,
            "date": date_short,
            "datetime": datetime_text,
            "place": place,
            "pref": pref_text,
            "status": status,
            "href": href,
            "alt": alt,
        }

        exams.append(
            exam
        )

    return exams


# ============================================================
# 10月対象判定
# ============================================================

def is_october_target(exam):

    if exam["year"] != 2026:
        return False

    if exam["month"] != 10:
        return False

    for ward in OCTOBER_TARGET_WARDS:

        if ward in exam["place"]:
            return True

    return False


# ============================================================
# 11月以降・大阪市対象判定
# ============================================================

def is_future_target(exam):

    if exam["year"] != 2026:
        return False

    if exam["month"] < FUTURE_MONTH:
        return False

    if "大阪市" not in exam["place"]:
        return False

    return True


# ============================================================
# 試験表示
# ============================================================

def exam_text(exam):

    status_text = {
        "open": "受付中",
        "full": "満員",
        "expired": "締切",
        "unknown": "不明",
    }

    return (
        f"{exam['datetime']}\n"
        f"場所：{exam['place']}\n"
        f"状態：{status_text.get(exam['status'], exam['status'])}\n"
        f"{exam['href']}"
    )


# ============================================================
# 監視処理
# ============================================================

def check_exams(state, first_check=False):

    html = get_page()

    exams = parse_exams(
        html
    )

    log(
        f"ページ解析完了：{len(exams)}件"
    )

    # --------------------------------------------------------
    # 今回取得した対象試験
    # --------------------------------------------------------

    october_exams = [
        e for e in exams
        if is_october_target(e)
    ]

    future_exams = [
        e for e in exams
        if is_future_target(e)
    ]

    log(
        f"10月大阪対象：{len(october_exams)}件"
    )

    log(
        f"11月以降大阪市：{len(future_exams)}件"
    )

    # --------------------------------------------------------
    # デバッグ用：対象試験を表示
    # --------------------------------------------------------

    for exam in october_exams:

        log(
            f"[10月対象] "
            f"{exam['date']} "
            f"{exam['datetime']} "
            f"{exam['place']} "
            f"→ {exam['status']}"
        )

    for exam in future_exams:

        log(
            f"[11月以降] "
            f"{exam['date']} "
            f"{exam['datetime']} "
            f"{exam['place']} "
            f"→ {exam['status']}"
        )

    # ========================================================
    # 初回チェック
    # ========================================================

    if first_check:

        log(
            "初回チェック：現在の状態を保存します"
        )

        for exam in october_exams:

            state["october"][
                exam["key"]
            ] = {
                "status": exam["status"],
                "datetime": exam["datetime"],
                "place": exam["place"],
                "href": exam["href"],
                "notified": False,
            }

        for exam in future_exams:

            state["future"][
                exam["key"]
            ] = {
                "status": exam["status"],
                "datetime": exam["datetime"],
                "place": exam["place"],
                "href": exam["href"],
                "notified": False,
            }

        save_state(
            state
        )

        return

    # ========================================================
    # 10月：満員 → 受付中
    # ========================================================

    for exam in october_exams:

        key = exam["key"]

        old = state["october"].get(
            key
        )

        if old is None:

            log(
                f"[10月] 新しい試験を検出："
                f"{exam['datetime']} "
                f"{exam['place']}"
            )

            state["october"][key] = {
                "status": exam["status"],
                "datetime": exam["datetime"],
                "place": exam["place"],
                "href": exam["href"],
                "notified": False,
            }

            continue

        old_status = old.get(
            "status"
        )

        new_status = exam["status"]

        if (
            old_status == "full"
            and
            new_status == "open"
            and
            not old.get("notified", False)
        ):

            message = (
                "🚨 MENSA大阪10月に空きが出ました！\n\n"
                + exam_text(exam)
            )

            log(
                f"★★★ 10月大阪に空き発生 ★★★ "
                f"{exam['datetime']} "
                f"{exam['place']}"
            )

            notify(
                "MENSA大阪10月 空き発生！",
                message
            )

            old["notified"] = True

        old["status"] = new_status

    # ========================================================
    # 11月以降：新規受付開始
    # ========================================================

    for exam in future_exams:

        key = exam["key"]

        old = state["future"].get(
            key
        )

        if old is None:

            log(
                f"[11月以降] 新規試験："
                f"{exam['datetime']} "
                f"{exam['place']} "
                f"→ {exam['status']}"
            )

            state["future"][key] = {
                "status": exam["status"],
                "datetime": exam["datetime"],
                "place": exam["place"],
                "href": exam["href"],
                "notified": False,
            }

            if (
                not first_check
                and
                exam["status"] == "open"
            ):

                message = (
                    "🚨 MENSA大阪市で11月以降の"
                    "新しい試験が受付開始！\n\n"
                    + exam_text(exam)
                )

                notify(
                    "MENSA大阪市 11月以降受付開始！",
                    message
                )

                state["future"][key][
                    "notified"
                ] = True

            continue

        old_status = old.get(
            "status"
        )

        new_status = exam["status"]

        if (
            old_status == "full"
            and
            new_status == "open"
            and
            not old.get("notified", False)
        ):

            message = (
                "🚨 MENSA大阪市で空きが出ました！\n\n"
                + exam_text(exam)
            )

            notify(
                "MENSA大阪市 11月以降 空き発生！",
                message
            )

            old["notified"] = True

        old["status"] = new_status

    # ========================================================
    # 保存
    # ========================================================

    save_state(
        state
    )


# ============================================================
# メイン
# ============================================================

def main():

    log(
        "=========================================="
    )

    log(
        "JAPAN MENSA 入会テスト監視開始"
    )

    log(
        "=========================================="
    )

    state = load_state()

    first_check = (
        not state["october"]
        and
        not state["future"]
    )

    start_time = time.time()

    try:

        while True:

            if (
                time.time() - start_time
                >= MAX_RUNTIME
            ):

                log(
                    "監視時間終了：今回の監視を終了します"
                )

                break

            try:

                check_exams(
                    state,
                    first_check
                )

                first_check = False

            except Exception as e:

                log(
                    f"通信・解析エラー：{e}"
                )

                notify(
                    "MENSA監視エラー",
                    str(e)
                )

            wait = random.randint(
                MIN_WAIT,
                MAX_WAIT
            )

            remaining = (
                MAX_RUNTIME
                - (time.time() - start_time)
            )

            if remaining <= 0:

                log(
                    "監視時間終了"
                )

                break

            wait = min(
                wait,
                int(remaining)
            )

            log(
                f"次回チェックまで {wait}秒"
            )

            time.sleep(
                wait
            )

    except KeyboardInterrupt:

        log(
            "監視を終了します"
        )


# ============================================================
# 実行
# ============================================================

if __name__ == "__main__":
    main()
