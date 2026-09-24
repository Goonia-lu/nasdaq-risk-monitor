import json
import urllib.request
from datetime import datetime, timezone


# ============================================================
# NASDAQ Risk Monitor v1.3
#
# 主要修复：
# 1. 修复 ^TNX 单位错误
# 2. 重新调整利率风险权重
# 3. 保存 history.json
# 4. Actions 日志完整输出核心数据
# ============================================================


def get_json(url):

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )


def get_history(symbol):

    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + symbol
        + "?range=1y&interval=1d"
    )

    data = get_json(url)

    result = data["chart"]["result"][0]

    timestamps = result["timestamp"]

    closes = result["indicators"]["quote"][0]["close"]

    values = []

    for timestamp, close in zip(
        timestamps,
        closes
    ):

        if close is not None:

            values.append({
                "timestamp": timestamp,
                "close": float(close)
            })

    return values


def clamp(
    value,
    minimum=0,
    maximum=100
):

    return max(
        minimum,
        min(maximum, value)
    )


def percentile_rank(
    values,
    current
):

    if not values:
        return 50

    below = sum(
        value <= current
        for value in values
    )

    return (
        below / len(values)
    ) * 100


def moving_average(
    values,
    period
):

    if len(values) < period:
        return None

    return sum(
        values[-period:]
    ) / period


def drawdown_from_peak(values):

    if not values:
        return 0

    peak = max(values)

    current = values[-1]

    return (
        current / peak - 1
    ) * 100


# ============================================================
# 1. 趋势风险
# ============================================================

def calculate_trend_risk(nasdaq):

    prices = [
        x["close"]
        for x in nasdaq
    ]

    current = prices[-1]

    ma50 = moving_average(
        prices,
        50
    )

    ma200 = moving_average(
        prices,
        200
    )

    risk50 = 0
    risk200 = 0

    if ma50:

        distance50 = (
            current / ma50 - 1
        ) * 100

        if distance50 < -10:
            risk50 = 100

        elif distance50 < -5:
            risk50 = 70

        elif distance50 < 0:
            risk50 = 40

        elif distance50 < 5:
            risk50 = 15

        else:
            risk50 = 0


    if ma200:

        distance200 = (
            current / ma200 - 1
        ) * 100

        if distance200 < -15:
            risk200 = 100

        elif distance200 < -10:
            risk200 = 85

        elif distance200 < 0:
            risk200 = 60

        elif distance200 < 5:
            risk200 = 25

        else:
            risk200 = 0


    risk = (
        risk50 * 0.4
        +
        risk200 * 0.6
    )

    return (
        clamp(risk),
        ma50,
        ma200
    )


# ============================================================
# 2. VIX
# ============================================================

def calculate_vix_risk(vix):

    values = [
        x["close"]
        for x in vix
    ]

    current = values[-1]

    percentile = percentile_rank(
        values,
        current
    )

    if len(values) >= 20:

        old = values[-20]

        change = (
            current / old - 1
        ) * 100

    else:

        change = 0


    change_risk = clamp(
        50 + change * 5
    )


    risk = (
        percentile * 0.7
        +
        change_risk * 0.3
    )


    return (
        clamp(risk),
        percentile,
        change
    )


# ============================================================
# 3. 利率风险
#
# 注意：
#
# Yahoo ^TNX:
#
#     5.11
#
# 就表示：
#
#     5.11%
#
# 这里绝对不能 /10。
#
# ============================================================

def calculate_rate_risk(tnx):

    values = [
        x["close"]
        for x in tnx
    ]

    current = values[-1]


    # --------------------------------------------------------
    # 当前水平
    # --------------------------------------------------------

    level_percentile = percentile_rank(
        values,
        current
    )


    # 当前水平虽然重要，
    # 但不能单独决定风险。
    #
    # 将 0~100 的历史分位压缩，
    # 防止高利率直接打满。
    level_risk = (
        level_percentile * 0.5
    )


    # --------------------------------------------------------
    # 20 日变化
    # --------------------------------------------------------

    changes20 = []

    for i in range(
        20,
        len(values)
    ):

        changes20.append(
            values[i]
            -
            values[i - 20]
        )


    if len(values) >= 21:

        change20 = (
            values[-1]
            -
            values[-21]
        )

    else:

        change20 = 0


    change20_percentile = percentile_rank(
        changes20,
        change20
    )


    # --------------------------------------------------------
    # 60 日变化
    # --------------------------------------------------------

    changes60 = []

    for i in range(
        60,
        len(values)
    ):

        changes60.append(
            values[i]
            -
            values[i - 60]
        )


    if len(values) >= 61:

        change60 = (
            values[-1]
            -
            values[-61]
        )

    else:

        change60 = 0


    change60_percentile = percentile_rank(
        changes60,
        change60
    )


    # --------------------------------------------------------
    # 综合
    #
    # 当前水平：20%
    # 20日变化：40%
    # 60日变化：40%
    # --------------------------------------------------------

    risk = (

        level_risk * 0.20

        +

        change20_percentile * 0.40

        +

        change60_percentile * 0.40

    )


    return (
        clamp(risk),
        current,
        level_percentile,
        change20,
        change60,
        change20_percentile,
        change60_percentile
    )


# ============================================================
# 4. 市场状态
# ============================================================

def calculate_market_risk(nasdaq):

    prices = [
        x["close"]
        for x in nasdaq
    ]

    current = prices[-1]


    if len(prices) >= 20:

        return20 = (
            current
            /
            prices[-20]
            -
            1
        ) * 100

    else:

        return20 = 0


    drawdown = drawdown_from_peak(
        prices
    )


    if return20 < -15:
        momentum_risk = 100

    elif return20 < -10:
        momentum_risk = 80

    elif return20 < -5:
        momentum_risk = 55

    elif return20 < 0:
        momentum_risk = 30

    else:
        momentum_risk = 5


    if drawdown < -20:
        drawdown_risk = 100

    elif drawdown < -15:
        drawdown_risk = 80

    elif drawdown < -10:
        drawdown_risk = 60

    elif drawdown < -5:
        drawdown_risk = 30

    else:
        drawdown_risk = 5


    risk = (
        momentum_risk * 0.45
        +
        drawdown_risk * 0.55
    )


    return (
        clamp(risk),
        return20,
        drawdown
    )


# ============================================================
# 5. 市场参与度代理
# ============================================================

def calculate_participation_risk(
    qqq,
    qqew
):

    qqq_prices = [
        x["close"]
        for x in qqq
    ]

    qqew_prices = [
        x["close"]
        for x in qqew
    ]


    n = min(
        len(qqq_prices),
        len(qqew_prices)
    )


    qqq_prices = qqq_prices[-n:]

    qqew_prices = qqew_prices[-n:]


    if n < 60:

        return (
            50,
            0
        )


    qqq_return = (
        qqq_prices[-1]
        /
        qqq_prices[-60]
        -
        1
    ) * 100


    qqew_return = (
        qqew_prices[-1]
        /
        qqew_prices[-60]
        -
        1
    ) * 100


    spread = (
        qqq_return
        -
        qqew_return
    )


    if spread >= 15:
        risk = 90

    elif spread >= 10:
        risk = 70

    elif spread >= 5:
        risk = 55

    elif spread >= 2:
        risk = 40

    else:
        risk = 20


    return (
        clamp(risk),
        spread
    )


# ============================================================
# 6. 总风险
# ============================================================

def calculate_total_risk(
    trend,
    volatility,
    rates,
    market,
    participation
):

    score = (

        trend * 0.30

        +

        volatility * 0.20

        +

        rates * 0.15

        +

        market * 0.25

        +

        participation * 0.10

    )


    return round(
        clamp(score)
    )


def risk_level(score):

    if score < 25:
        return "低风险"

    if score < 45:
        return "中等风险"

    if score < 65:
        return "较高风险"

    if score < 80:
        return "高风险"

    return "极高风险"


# ============================================================
# 7. 保存历史
# ============================================================

def save_history(
    score,
    trend,
    volatility,
    rates,
    market,
    participation
):

    today = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d"
    )


    try:

        with open(
            "history.json",
            "r",
            encoding="utf-8"
        ) as f:

            history = json.load(f)

    except:

        history = []


    record = {

        "date": today,

        "score": score,

        "trend": round(trend),

        "volatility":
            round(volatility),

        "rates":
            round(rates),

        "market":
            round(market),

        "participation":
            round(participation)
    }


    # 同一天重新运行：
    # 替换旧记录。

    history = [
        item
        for item in history
        if item.get("date") != today
    ]


    history.append(
        record
    )


    # 最多保存约一年

    history = history[-370:]


    with open(
        "history.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            history,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# 主程序
# ============================================================

def main():

    print(
        "正在获取市场数据……"
    )


    nasdaq = get_history("^IXIC")

    vix = get_history("^VIX")

    tnx = get_history("^TNX")

    qqq = get_history("QQQ")

    qqew = get_history("QQEW")


    if not nasdaq:
        raise Exception(
            "无法获取 Nasdaq 数据"
        )

    if not vix:
        raise Exception(
            "无法获取 VIX 数据"
        )

    if not tnx:
        raise Exception(
            "无法获取10年期国债数据"
        )

    if not qqq:
        raise Exception(
            "无法获取 QQQ 数据"
        )

    if not qqew:
        raise Exception(
            "无法获取 QQEW 数据"
        )


    # ========================================================
    # 计算
    # ========================================================

    (
        trend_risk,
        ma50,
        ma200
    ) = calculate_trend_risk(
        nasdaq
    )


    (
        volatility_risk,
        vix_percentile,
        vix_change
    ) = calculate_vix_risk(
        vix
    )


    (
        rate_risk,
        treasury10y,
        rate_percentile,
        rate_change20,
        rate_change60,
        rate_change20_percentile,
        rate_change60_percentile

    ) = calculate_rate_risk(
        tnx
    )


    (
        market_risk,
        return20,
        drawdown
    ) = calculate_market_risk(
        nasdaq
    )


    (
        participation_risk,
        participation_spread

    ) = calculate_participation_risk(
        qqq,
        qqew
    )


    score = calculate_total_risk(

        trend_risk,

        volatility_risk,

        rate_risk,

        market_risk,

        participation_risk
    )


    level = risk_level(score)


    nasdaq_current = (
        nasdaq[-1]["close"]
    )

    vix_current = (
        vix[-1]["close"]
    )


    # ========================================================
    # data.json
    # ========================================================

    data = {

        "updated":
            datetime.now(
                timezone.utc
            ).strftime(
                "%Y-%m-%d"
            ),

        "risk_score":
            score,

        "risk_level":
            level,

        "model_version":
            "1.3",


        "indicators": {

            "nasdaq": {

                "name":
                    "纳斯达克",

                "value":
                    round(
                        nasdaq_current,
                        2
                    ),

                "status":
                    "正常"
            },


            "vix": {

                "name":
                    "VIX",

                "value":
                    round(
                        vix_current,
                        2
                    ),

                "status":

                    (
                        "高"
                        if vix_current >= 30

                        else
                        "偏高"
                        if vix_current >= 25

                        else
                        "中等"
                        if vix_current >= 20

                        else
                        "较低"
                    )
            },


            "treasury10y": {

                "name":
                    "美国10年期国债收益率",

                "value":
                    round(
                        treasury10y,
                        3
                    ),

                "status":

                    (
                        "偏高"
                        if treasury10y >= 5

                        else
                        "中等"
                        if treasury10y >= 4

                        else
                        "较低"
                    )
            },


            "participation": {

                "name":
                    "市场参与度",

                "value":
                    round(
                        participation_spread,
                        2
                    ),

                "status":

                    (
                        "集中度偏高"
                        if participation_spread >= 10

                        else
                        "略偏集中"
                        if participation_spread >= 5

                        else
                        "正常"
                    )
            }
        },


        "risk_components": {

            "trend":
                round(trend_risk),

            "volatility":
                round(volatility_risk),

            "rates":
                round(rate_risk),

            "market":
                round(market_risk),

            "participation":
                round(participation_risk)
        },


        "details": {

            "nasdaq_ma50":
                round(
                    ma50,
                    2
                ) if ma50 else None,

            "nasdaq_ma200":
                round(
                    ma200,
                    2
                ) if ma200 else None,

            "vix_percentile":
                round(
                    vix_percentile,
                    1
                ),

            "vix_20d_change":
                round(
                    vix_change,
                    2
                ),

            "treasury10y":
                round(
                    treasury10y,
                    3
                ),

            "treasury_percentile":
                round(
                    rate_percentile,
                    1
                ),

            "treasury_20d_change":
                round(
                    rate_change20,
                    3
                ),

            "treasury_60d_change":
                round(
                    rate_change60,
                    3
                ),

            "treasury_20d_change_percentile":
                round(
                    rate_change20_percentile,
                    1
                ),

            "treasury_60d_change_percentile":
                round(
                    rate_change60_percentile,
                    1
                ),

            "nasdaq_20d_return":
                round(
                    return20,
                    2
                ),

            "nasdaq_drawdown":
                round(
                    drawdown,
                    2
                ),

            "qqq_qqew_60d_spread":
                round(
                    participation_spread,
                    2
                )
        }
    }


    with open(
        "data.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


    # 保存历史

    save_history(

        score,

        trend_risk,

        volatility_risk,

        rate_risk,

        market_risk,

        participation_risk
    )


    # ========================================================
    # 完整输出
    # ========================================================

    print("")
    print("========================================")
    print(" NASDAQ RISK MONITOR v1.3")
    print("========================================")

    print(f"Risk Score       : {score}")
    print(f"Risk Level       : {level}")
    print("")

    print("Risk Components")
    print("----------------------------------------")

    print(
        f"Trend            : {trend_risk:.1f}"
    )

    print(
        f"Volatility       : {volatility_risk:.1f}"
    )

    print(
        f"Rates            : {rate_risk:.1f}"
    )

    print(
        f"Market           : {market_risk:.1f}"
    )

    print(
        f"Participation    : "
        f"{participation_risk:.1f}"
    )

    print("")

    print("Market Details")
    print("----------------------------------------")

    print(
        f"Nasdaq           : "
        f"{nasdaq_current:.2f}"
    )

    print(
        f"MA50             : "
        f"{ma50:.2f}"
    )

    print(
        f"MA200            : "
        f"{ma200:.2f}"
    )

    print(
        f"20d Return       : "
        f"{return20:+.2f}%"
    )

    print(
        f"Drawdown         : "
        f"{drawdown:.2f}%"
    )

    print("")

    print("Volatility")
    print("----------------------------------------")

    print(
        f"VIX              : "
        f"{vix_current:.2f}"
    )

    print(
        f"VIX Percentile   : "
        f"{vix_percentile:.1f}%"
    )

    print(
        f"VIX 20d Change   : "
        f"{vix_change:+.2f}%"
    )

    print("")

    print("Rates")
    print("----------------------------------------")

    print(
        f"10Y Yield        : "
        f"{treasury10y:.3f}%"
    )

    print(
        f"10Y Percentile   : "
        f"{rate_percentile:.1f}%"
    )

    print(
        f"10Y 20d Change   : "
        f"{rate_change20:+.3f} pp"
    )

    print(
        f"10Y 60d Change   : "
        f"{rate_change60:+.3f} pp"
    )

    print(
        f"20d Change Pctl  : "
        f"{rate_change20_percentile:.1f}%"
    )

    print(
        f"60d Change Pctl  : "
        f"{rate_change60_percentile:.1f}%"
    )

    print("")

    print("Participation")
    print("----------------------------------------")

    print(
        f"QQQ/QQEW Spread  : "
        f"{participation_spread:+.2f}%"
    )

    print("")

    print("History saved to history.json")
    print("========================================")


if __name__ == "__main__":

    main()