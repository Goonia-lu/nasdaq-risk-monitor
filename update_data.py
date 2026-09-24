import json
import urllib.request
from datetime import datetime, timezone
# ============================================================
# NASDAQ Risk Monitor v1.1
#
# 修复：
#   ^TNX Yahoo 数据需要 /10 才是百分比收益率
#
# 新增：
#   QQQ / QQEW 参与度代理
#
# 当前模块：
#   1. 趋势
#   2. 波动率
#   3. 利率
#   4. 市场状态
#   5. 参与度代理
# ============================================================
def get_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
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
    closes = result[
        "indicators"
    ]["quote"][0]["close"]
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
def moving_average(values, period):
    if len(values) < period:
        return None
    return sum(
        values[-period:]
    ) / period
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
# 2. VIX 风险
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
# 关键修复：
#
# Yahoo ^TNX:
#
#     49.68
#
# 实际表示：
#
#     4.968%
#
# 因此这里统一 /10。
# ============================================================
def calculate_rate_risk(tnx):
    raw_values = [
        x["close"]
        for x in tnx
    ]
    # 转换成真正的百分比收益率
    values = [
        value / 10
        for value in raw_values
    ]
    current = values[-1]
    percentile = percentile_rank(
        values,
        current
    )
    if len(values) >= 20:
        old = values[-20]
        change = (
            current - old
        )
    else:
        change = 0
    # 当前利率水平风险
    #
    # 这里不再简单认为
    # “高于4% = 高风险”。
    #
    # 主要看历史位置。
    level_risk = percentile
    # 20日快速上行才额外增加压力
    if change >= 0.50:
        shock_risk = 90
    elif change >= 0.30:
        shock_risk = 70
    elif change >= 0.15:
        shock_risk = 55
    elif change >= 0:
        shock_risk = 40
    else:
        shock_risk = 20
    risk = (
        level_risk * 0.65
        +
        shock_risk * 0.35
    )
    return (
        clamp(risk),
        current,
        percentile,
        change
    )
# ============================================================
# 4. 市场状态风险
# ============================================================
def calculate_market_risk(nasdaq):
    prices = [
        x["close"]
        for x in nasdaq
    ]
    current = prices[-1]
    if len(prices) >= 20:
        return20 = (
            current / prices[-20] - 1
        ) * 100
    else:
        return20 = 0
    drawdown = drawdown_from_peak(
        prices
    )
    # 20日动量
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
    # 回撤
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
#
# QQQ:
#   市值加权 Nasdaq-100 ETF
#
# QQEW:
#   等权相关 Nasdaq-100 产品
#
# 如果 QQQ 明显跑赢 QQEW，
# 说明大型成分股对指数贡献更强。
#
# 这不是严格意义上的市场宽度，
# 所以暂时只占 10%。
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
        - 1
    ) * 100
    qqew_return = (
        qqew_prices[-1]
        /
        qqew_prices[-60]
        - 1
    ) * 100
    spread = (
        qqq_return
        -
        qqew_return
    )
    # 大盘股明显跑赢等权：
    # 市场内部可能更依赖少数大型股票。
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
# 综合风险
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
# 主程序
# ============================================================
def main():
    print(
        "正在获取市场数据……"
    )
    nasdaq = get_history(
        "^IXIC"
    )
    vix = get_history(
        "^VIX"
    )
    tnx = get_history(
        "^TNX"
    )
    qqq = get_history(
        "QQQ"
    )
    qqew = get_history(
        "QQEW"
    )
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
    # -------------------------
    # 风险模块
    # -------------------------
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
        rate_change
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
    # -------------------------
    # 总分
    # -------------------------
    score = calculate_total_risk(
        trend_risk,
        volatility_risk,
        rate_risk,
        market_risk,
        participation_risk
    )
    level = risk_level(
        score
    )
    # -------------------------
    # 当前市场数据
    # -------------------------
    nasdaq_current = (
        nasdaq[-1]["close"]
    )
    vix_current = (
        vix[-1]["close"]
    )
    # -------------------------
    # 输出
    # -------------------------
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
            "1.1",
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
                round(
                    trend_risk
                ),
            "volatility":
                round(
                    volatility_risk
                ),
            "rates":
                round(
                    rate_risk
                ),
            "market":
                round(
                    market_risk
                ),
            "participation":
                round(
                    participation_risk
                )
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
                    rate_change,
                    3
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
    print(
        "--------------------------------"
    )
    print(
        f"NASDAQ Risk Score: {score}"
    )
    print(
        f"Risk Level: {level}"
    )
    print(
        "Components:"
    )
    print(
        f"  Trend: {trend_risk:.1f}"
    )
    print(
        f"  Volatility: {volatility_risk:.1f}"
    )
    print(
        f"  Rates: {rate_risk:.1f}"
    )
    print(
        f"  Market: {market_risk:.1f}"
    )
    print(
        f"  Participation: "
        f"{participation_risk:.1f}"
    )
    print(
        "--------------------------------"
    )
if __name__ == "__main__":
    main()