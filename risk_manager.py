class RiskManager:
    def __init__(self):
        self.consecutive_losses = 0
        self.max_losses = 5
        self.max_risk_per_trade = 0.05

    def calculate_risk_multiplier(self, balance, confidence, consecutive_losses=None):
        if consecutive_losses is not None:
            self.consecutive_losses = consecutive_losses
        kelly_fraction = confidence / 100.0 if confidence > 0 else 0.1
        kelly_fraction = min(kelly_fraction, 0.25)
        loss_penalty = 0.8 ** self.consecutive_losses
        risk = kelly_fraction * loss_penalty
        risk = min(risk, self.max_risk_per_trade)
        risk = max(risk, 0.01)
        return risk

    def update_losses(self, win):
        if win:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            if self.consecutive_losses > self.max_losses:
                self.consecutive_losses = self.max_losses
