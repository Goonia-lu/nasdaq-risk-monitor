import json
import urllib.request
from datetime import datetime, timezone
# ============================================================
# NASDAQ Risk Monitor
# 第一版正式风险模型
#
# 数据：
#   ^IXIC  Nasdaq Composite
#   ^VIX   CBOE Volatility Index
#   ^TNX   US 10Y Treasury Yield
#
# 风险分数：
#   0   = 风险较低
#   100 = 风险极高
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
def get_history(symbol, days=260):
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
    return values[-days:]
def moving_average(values, period):
    if len(values) < period:
        return None
    recent = values[-period:]
    return sum(
        recent
    ) / period
def drawdown_from_peak(values):
    if not values:
        return 0
    peak = max(values)
    current = values[-1]
    return (
        current / peak - 1
    ) * 100
def percentile_rank(values, current):
    if not values:
        return 50
    below = sum(
        value <= current
        for value in values
    )
    return (
        below / len(values)
    ) * 100
def clamp(value, minimum=0, maximum=100):
    return max(
        minimum,
        min(maximum, value)
    )
# ============================================================
# 趋势风险
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
    risk = 0
    # 当前价格相对 50 日均线
    if ma50:
        distance50 = (
            current / ma50 - 1
        ) * 100
        if distance50 < -10:
            risk += 35
        elif distance50 < -5:
            risk += 25
        elif distance50 < 0:
            risk += 12
        elif distance50 < 5:
            risk += 5
    # 当前价格相对 200 日均线
    if ma200:
        distance200 = (
            current / ma200 - 1
        ) * 100
        if distance200 < -15:
            risk += 65
        elif distance200 < -10:
            risk += 50
        elif distance200 < 0:
            risk += 30
        elif distance200 < 5:
            risk += 15
        else:
            risk += 0
    return clamp(risk / 1.0), ma50, ma200
# ============================================================
# VIX 风险
# ============================================================
def calculate_vix_risk(vix):
    values = [
        x["close"]
        for x in vix
    ]
    current = values[-1]
    # 历史分位数
    percentile = percentile_rank(
        values,
        current
    )
    # 最近 20 日变化
    if len(values) >= 20:
        old = values[-20]
        change = (
            current / old - 1
        ) * 100
    else:
        change = 0
    # 历史位置占 70%
    # 最近变化占 30%
    risk = (
        percentile * 0.70
        +
        clamp(
            50 + change * 5
        ) * 0.30
    )
    return clamp(risk), percentile, change
# ============================================================
# 利率风险
# ============================================================
def calculate_rate_risk(tnx):
    values = [
        x["close"]
        for x in tnx
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
    # 利率本身的历史位置
    # + 最近变化
    risk = (
        percentile * 0.75
        +
        clamp(
            50 + change * 20
        ) * 0.25
    )
    return clamp(risk), percentile, change
# ============================================================
# 市场状态
# ============================================================
def calculate_market_risk(nasdaq):
    prices = [
        x["close"]
        for x in nasdaq
    ]
    current = prices[-1]
    # 20 日收益率
    if len(prices) >= 20:
        return20 = (
            current / prices[-20] - 1
        ) * 100
    else:
        return20 = 0
    # 当前距过去一年最高点的回撤
    drawdown = drawdown_from_peak(
        prices
    )
    risk = 0
    # 动量越差，风险越高
    if return20 < -15:
        risk += 80
    elif return20 < -10:
        risk += 60
    elif return20 < -5:
        risk += 40
    elif return20 < 0:
        risk += 20
    else:
        risk += 5
    # 回撤
    if drawdown < -20:
        risk += 100
    elif drawdown < -15:
        risk += 80
    elif drawdown < -10:
        risk += 60
    elif drawdown < -5:
        risk += 30
    else:
        risk += 5
    risk /= 2
    return clamp(risk), return20, drawdown
# ============================================================
# 总风险
# ============================================================
def calculate_total_risk(
    trend,
    volatility,
    rates,
    market
):
    score = (
        trend * 0.35
        +
        volatility * 0.25
        +
        rates * 0.15
        +
        market * 0.25
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
    print("正在获取市场数据……")
    nasdaq = get_history(
        "^IXIC",
        260
    )
    vix = get_history(
        "^VIX",
        260
    )
    tnx = get_history(
        "^TNX",
        260
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
            "无法获取美国10年期国债数据"
        )
    # -------------------------
    # 各模块风险
    # -------------------------
    trend_risk, ma50, ma200 = (
        calculate_trend_risk(
            nasdaq
        )
    )
    volatility_risk, vix_percentile, vix_change = (
        calculate_vix_risk(
            vix
        )
    )
    rate_risk, rate_percentile, rate_change = (
        calculate_rate_risk(
            tnx
        )
    )
    market_risk, return20, drawdown = (
        calculate_market_risk(
            nasdaq
        )
    )
    # -------------------------
    # 总分
    # -------------------------
    score = calculate_total_risk(
        trend_risk,
        volatility_risk,
        rate_risk,
        market_risk
    )
    level = risk_level(
        score
    )
    # -------------------------
    # 当前值
    # -------------------------
    nasdaq_current = nasdaq[-1]["close"]
    vix_current = vix[-1]["close"]
    tnx_current = tnx[-1]["close"]
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
            "1.0",
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
                        tnx_current,
                        2
                    ),
                "status":
                    (
                        "偏高"
                        if tnx_current >= 5
                        else
                        "中等"
                        if tnx_current >= 4
                        else
                        "较低"
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
        f"风险分数：{score}"
    )
    print(
        f"风险等级：{level}"
    )
    print(
        "数据更新完成。"
    )
if __name__ == "__main__":
    main()