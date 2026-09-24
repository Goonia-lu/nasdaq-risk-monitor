import json
import urllib.request
from datetime import datetime, timezone


def get_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def get_yahoo_price(symbol):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + symbol
        + "?range=5d&interval=1d"
    )

    data = get_json(url)

    result = data["chart"]["result"][0]

    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]

    values = [
        (timestamp, close)
        for timestamp, close in zip(timestamps, closes)
        if close is not None
    ]

    return values[-1][1]


def calculate_risk(nasdaq, vix, treasury10y):
    """
    第一版只是测试算法。

    后面我们会把这里升级成真正的
    多指标风险模型。
    """

    score = 0

    # VIX
    if vix >= 30:
        score += 30
    elif vix >= 25:
        score += 20
    elif vix >= 20:
        score += 10

    # 10Y Treasury
    if treasury10y >= 5:
        score += 20
    elif treasury10y >= 4.5:
        score += 15
    elif treasury10y >= 4:
        score += 8

    # 纳斯达克趋势
    # 第一版暂时只保留一个基础占位项
    score += 5

    score = min(score, 100)

    if score < 25:
        level = "低风险"
    elif score < 50:
        level = "中等风险"
    elif score < 70:
        level = "较高风险"
    else:
        level = "高风险"

    return score, level


def main():

    # Nasdaq Composite
    nasdaq = get_yahoo_price("^IXIC")

    # VIX
    vix = get_yahoo_price("^VIX")

    # 10Y Treasury Yield
    treasury10y = get_yahoo_price("^TNX")

    risk_score, risk_level = calculate_risk(
        nasdaq,
        vix,
        treasury10y
    )

    data = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),

        "risk_score": risk_score,

        "risk_level": risk_level,

        "indicators": {

            "nasdaq": {
                "name": "纳斯达克",
                "value": round(nasdaq, 2),
                "status": "正常"
            },

            "vix": {
                "name": "VIX",
                "value": round(vix, 2),
                "status":
                    "偏高" if vix >= 25
                    else "中等" if vix >= 20
                    else "较低"
            },

            "treasury10y": {
                "name": "美国10年期国债收益率",
                "value": round(treasury10y, 2),
                "status":
                    "偏高" if treasury10y >= 4.5
                    else "中等" if treasury10y >= 4
                    else "较低"
            }
        }
    }

    with open("data.json", "w", encoding="utf-8") as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


if __name__ == "__main__":
    main()