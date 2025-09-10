import numpy as np
from data import pre_load_ohlc, get_external_data

class Agent:
    def __init__(self, name):
        self.name = name
        self.conviction_history = []
        self.weight = 0.5

    def update_history(self, success):
        self.conviction_history.append(success)
        if len(self.conviction_history) > 100:
            self.conviction_history.pop(0)
        self.weight = max(0.1, min(0.9, np.mean(self.conviction_history) if self.conviction_history else 0.5))

    def get_weight(self):
        return self.weight

class AgentSystem:
    def __init__(self, pairs):
        self.agents = {
            'momentum': Agent('momentum'),
            'sentiment': Agent('sentiment'),
            'market_data': Agent('market_data'),
            'meta': Agent('meta'),
            'sandbox': Agent('sandbox')
        }
        self.pairs = pairs

    def get_signals(self, price, ohlc, volume, atr, external_data):
        signals = {}
        closes = [float(c[4]) for c in ohlc[-14:]]  # 14 periods for RSI
        rsi = np.mean([1 if closes[i] > closes[i-1] else 0 for i in range(1, len(closes))]) if len(closes) > 1 else 0.5
        ext_volume = external_data.get('volume_24h', 0)

        # Momentum
        momentum_conviction = abs(rsi - 0.5) + (atr / price) + (volume / 1000000) + (ext_volume / 1000000)
        signals['momentum'] = (min(momentum_conviction, 0.3) * self.agents['momentum'].get_weight(), 'SELL' if rsi < 0.4 else 'BUY')

        # Sentiment
        change_24h = (price - float(ohlc[0][4])) / float(ohlc[0][4]) if ohlc else 0
        signals['sentiment'] = (min(abs(change_24h), 0.045) * self.agents['sentiment'].get_weight(), 'BUY' if change_24h > 0 else 'SELL')

        # Market Data
        last_change = (float(ohlc[-1][4]) - float(ohlc[-2][4])) / float(ohlc[-2][4]) if len(ohlc) > 1 else 0
        market_conviction = abs(last_change) + (volume / 1000000) + (atr / price) + (ext_volume / 1000000)
        signals['market_data'] = (min(market_conviction, 0.065) * self.agents['market_data'].get_weight(), 'SELL' if last_change < 0 else 'BUY')

        # Meta
        meta_conviction = min(sum(v[0] for v in signals.values()) / len(signals), 0.125) * self.agents['meta'].get_weight()
        signals['meta'] = (meta_conviction, signals['momentum'][1])

        # Sandbox
        sandbox_conviction = min(signals['market_data'][0] * 0.9, 0.08) * self.agents['sandbox'].get_weight()
        signals['sandbox'] = (sandbox_conviction, 'SELL' if signals['market_data'][1] == 'BUY' else 'BUY')

        return signals

    def adjust_convictions(self, gpt_adjustment):
        for agent in self.agents.values():
            if "increase" in gpt_adjustment.lower():
                agent.conviction_history = [min(v + 0.1, 1.0) for v in agent.conviction_history]
            elif "decrease" in gpt_adjustment.lower():
                agent.conviction_history = [max(v - 0.1, 0.0) for v in agent.conviction_history]
            agent.update_history(0.5)  # Placeholder success