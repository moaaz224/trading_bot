import requests
import os

class SentimentAnalyzer:
    def __init__(self):
        self.news_api_key = os.getenv('NEWS_API_KEY', '')
        self.cache = {}

    def analyze(self, asset_name='EURUSD'):
        return 0.0 # تحليل وهمي للتجربة
