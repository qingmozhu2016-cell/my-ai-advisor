"""
financial_report.py - 家庭财富风险管理日报生成器
GitHub Actions 每日定时运行
"""
import asyncio
import logging
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr

import aiohttp
import yfinance as yf
import feedparser
import markdown
from pydantic_settings import BaseSettings
from jinja2 import Template
from google import genai


# ============================================================
# 配置管理
# ============================================================

class Settings(BaseSettings):
    """从环境变量加载配置"""
    gemini_api_key: str = ""
    email_user: str = ""
    email_pass: str = ""
    email_to: str = ""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    report_dir: str = "./AI_Reports"


settings = Settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


# ============================================================
# 数据模型
# ============================================================

@dataclass
class MarketQuote:
    """资产行情数据"""
    name: str
    price: float
    change_pct: float
    formatted_price: str = ""
    
    @property
    def icon(self) -> str:
        return "🔺" if self.change_pct > 0 else "💚"
    
    def to_table_row(self) -> str:
        display_price = self.formatted_price or f"{self.price:.2f}"
        return f"| {self.name} | {display_price} | {self.icon} {self.change_pct:+.2f}% |"


# ============================================================
# 行情获取器
# ============================================================

class MarketFetcher:
    """行情数据获取器"""
    
    SINA_TICKERS = [
        ('sh000001', '🇨🇳 上证指数', None),
        ('sz399006', '🇨🇳 创业板指', None),
        ('sh518880', '🟡 黄金价格(CNY)', lambda p: f"{p * 100:.2f} 元/克"),
    ]
    
    YAHOO_TICKERS = [
        ('CNY=X', '💱 美元/人民币', lambda p: f"{p:.4f}"),
        ('BTC-USD', '🪙 比特币', lambda p: f"$ {p:,.2f}"),
        ('^TNX', '🇺🇸 10年美债', lambda p: f"{p:.3f}%"),
    ]

    async def fetch_sina(self, session: aiohttp.ClientSession, code: str, name: str, formatter) -> Optional[MarketQuote]:
        """异步获取新浪数据"""
        url = f"http://hq.sinajs.cn/list={code}"
        headers = {'Referer': 'https://finance.sina.com.cn'}
        
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                text = await resp.text()
                if "," not in text:
                    return None
                
                data = text.split('"')[1].split(',')
                price = float(data[3]) or float(data[2])
                prev_close = float(data[2])
                change_pct = ((price - prev_close) / prev_close) * 100
                
                formatted = formatter(price) if formatter else None
                return MarketQuote(name, price, change_pct, formatted)
        except Exception as e:
            logger.warning(f"新浪接口异常 ({name}): {e}")
            return None

    def fetch_yahoo_sync(self, symbol: str, name: str, formatter) -> Optional[MarketQuote]:
        """Yahoo 同步获取"""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="2d", interval="60m")
            if df.empty:
                return None
            
            price = df['Close'].iloc[-1]
            prev = df['Close'].iloc[0]
            change_pct = ((price - prev) / prev) * 100
            
            formatted = formatter(price) if formatter else None
            return MarketQuote(name, price, change_pct, formatted)
        except Exception as e:
            logger.warning(f"Yahoo 接口异常 ({name}): {e}")
            return None

    async def fetch_all(self) -> list[MarketQuote]:
        """并发获取所有行情"""
        quotes = []
        
        async with aiohttp.ClientSession() as session:
            sina_tasks = [
                self.fetch_sina(session, code, name, fmt) 
                for code, name, fmt in self.SINA_TICKERS
            ]
            sina_results = await asyncio.gather(*sina_tasks)
            quotes.extend([q for q in sina_results if q])
        
        loop = asyncio.get_event_loop()
        yahoo_tasks = [
            loop.run_in_executor(None, self.fetch_yahoo_sync, sym, name, fmt)
            for sym, name, fmt in self.YAHOO_TICKERS
        ]
        yahoo_results = await asyncio.gather(*yahoo_tasks)
        quotes.extend([q for q in yahoo_results if q])
        
        return quotes


# ============================================================
# 新闻聚合器
# ============================================================

class NewsFetcher:
    """新闻 RSS 聚合器"""
    
    SOURCES = [
        ("新浪财经", "http://rss.sina.com.cn/roll/finance/hot_roll.xml", 6),
        ("联合早报", "https://www.zaobao.com.sg/rss/finance.xml", 3),
        ("Yahoo", "https://finance.yahoo.com/news/rssindex", 3),
    ]

    async def fetch_feed(self, session: aiohttp.ClientSession, name: str, url: str, count: int) -> list[str]:
        """异步获取单个 RSS"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                text = await resp.text()
                feed = feedparser.parse(text)
                return [f"【{name}】{entry.title}" for entry in feed.entries[:count]]
        except Exception as e:
            logger.warning(f"RSS 获取失败 ({name}): {e}")
            return []

    async def fetch_all(self) -> str:
        """并发获取所有新闻源"""
        logger.info("🌍 正在聚合新闻...")
        
        async with aiohttp.ClientSession() as session:
            tasks = [
                self.fetch_feed(session, name, url, count)
                for name, url, count in self.SOURCES
            ]
            results = await asyncio.gather(*tasks)
        
        all_news = [item for sublist in results for item in sublist]
        return "\n".join(all_news)


# ============================================================
# 邮件发送器
# ============================================================

EMAIL_TEMPLATE = Template("""
<!DOCTYPE html>
<html>
<head>
<style>
    body { font-family: -apple-system, system-ui, "Microsoft YaHei", sans-serif; 
           line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 15px; }
    h1 { font-size: 20px; color: #111; border-bottom: 2px solid #eee; padding-bottom: 10px; }
    h2 { font-size: 18px; color: #b71c1c; margin-top: 35px; border-left: 4px solid #b71c1c; padding-left: 10px; }
    h3 { font-size: 16px; font-weight: bold; margin-top: 25px; color: #0d47a1; }
    p { margin-bottom: 15px; text-align: justify; font-size: 15px; }
    table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; 
            box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 4px; overflow: hidden; }
    th, td { border: 1px solid #e1e4e8; padding: 8px 5px; text-align: center; }
    th { background-color: #f6f8fa; font-weight: bold; }
    blockquote { border-left: 4px solid #f9a825; background: #fffde7; 
                 padding: 15px; margin: 20px 0; border-radius: 6px; font-style: italic; }
    strong { color: #d32f2f; }
    .footer { font-size: 12px; color: #999; margin-top: 40px; text-align: center; 
              border-top: 1px solid #eee; padding-top: 10px; }
</style>
</head>
<body>
{{ content }}
<div class="footer">本报告由 AI 辅助生成，仅供参考，不构成投资建议。</div>
</body>
</html>
""")


class EmailSender:
    """邮件发送器"""
    
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, title: str, md_content: str, attachment_path: Optional[str] = None) -> bool:
        """发送 HTML 邮件"""
        if not self.settings.email_user:
            logger.warning("⚠️ 未配置邮箱，跳过发送")
            return False
        
        msg = MIMEMultipart()
        msg['Subject'] = title
        msg['From'] = formataddr(("朱文翔的AI助理", self.settings.email_user))
        msg['To'] = self.settings.email_to
        
        html_body = markdown.markdown(md_content, extensions=['tables'])
        full_html = EMAIL_TEMPLATE.render(content=html_body)
        msg.attach(MIMEText(full_html, 'html'))
        
        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
            part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
            msg.attach(part)
        
        try:
            with smtplib.SMTP(self.settings.smtp_server, self.settings.smtp_port) as server:
                server.starttls()
                server.login(self.settings.email_user, self.settings.email_pass)
                server.sendmail(self.settings.email_user, [self.settings.email_to], msg.as_string())
            logger.info("✅ 邮件已发送！")
            return True
        except Exception as e:
            logger.error(f"❌ 发送失败: {e}")
            return False


# ============================================================
# 报告生成器
# ============================================================

REPORT_PROMPT = """
【角色设定】
你叫朱文翔，一名资深、稳健的投资顾问。
你的读者是**有一定资产、但风险偏好较低的保险意向客户**。

【核心理念】
你信奉**全天候策略 (All-Weather)** 和 **反脆弱**，强调利用保险和固收资产作为家庭财富的"压舱石"。

【日期】{date}

【素材】
1. 行情：
{market_table}

2. 新闻池：
{news}

【任务】撰写《家庭财富风险管理日报》。

【结构要求】

**第一部分：核心资产看板**
- 展示表格，用大白话简评市场。

**第二部分：财经要闻（Top 5）**
- 筛选 5 条最重要新闻，其中至少 1 条中国国内宏观/政策新闻。
- 格式：`1. [标题]` -> `[一句话事实]` -> `> 💡 对家庭财富的影响：...`

**第三部分：历史映照与行动指南**

1. **【今日锚点】**：挑一个热点话题。

2. **【历史回响】**：用一个历史案例（如大萧条、郁金香泡沫等）映射今日新闻，传递长期主义理念。

3. **【给您的建议】**：
   - 结合今日行情给出简短建议
   - 展示《家庭资产全天候配置参考表》（Markdown 表格）：
   
| 资产角色 | 建议比例 | 典型标的 | 作用 |
| :--- | :--- | :--- | :--- |
| **进攻矛** | 20-30% | 优质股票/权益基金 | 博取长期超额收益 |
| **防御盾** | 40-50% | 年金险/增额寿/国债 | 锁定利率，家庭兜底 |
| **避风港** | 10-20% | 黄金/硬通货 | 对冲极端风险 |
| **现金流** | 10% | 货币基金/活期 | 随时应急 |
"""


class ReportGenerator:
    """日报生成器"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.market_fetcher = MarketFetcher()
        self.news_fetcher = NewsFetcher()
        self.email_sender = EmailSender(settings)

    def _build_market_table(self, quotes: list[MarketQuote]) -> str:
        """构建行情表格"""
        header = "| 资产 | 最新价 | 涨跌幅 |\n|---|---|---|\n"
        rows = "\n".join(q.to_table_row() for q in quotes)
        return header + rows

    async def generate(self) -> Optional[str]:
        """生成报告"""
        date_str = datetime.now().strftime('%Y-%m-%d')
        
        logger.info("📊 正在同步行情...")
        quotes, news = await asyncio.gather(
            self.market_fetcher.fetch_all(),
            self.news_fetcher.fetch_all()
        )
        
        market_table = self._build_market_table(quotes)
        
        logger.info("🤖 Gemini 正在构思...")
        prompt = REPORT_PROMPT.format(
            date=date_str,
            market_table=market_table,
            news=news
        )
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt
            )
            
            if not response.text:
                logger.error("❌ 生成内容为空")
                return None
            
            os.makedirs(self.settings.report_dir, exist_ok=True)
            filepath = os.path.join(self.settings.report_dir, f"{date_str}_AI_Daily.md")
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info(f"📄 报告已保存: {filepath}")
            
            self.email_sender.send(
                title=f"【内参】{date_str} 历史映照与配置建议",
                md_content=response.text,
                attachment_path=filepath
            )
            
            return response.text
            
        except Exception as e:
            logger.error(f"❌ 生成失败: {e}")
            return None


# ============================================================
# 程序入口
# ============================================================

async def main():
    """主函数"""
    logger.info("🚀 启动日报生成器...")
    
    generator = ReportGenerator(settings)
    report = await generator.generate()
    
    if report:
        logger.info("✅ 日报生成完成！")
    else:
        logger.error("❌ 日报生成失败")


if __name__ == "__main__":
    asyncio.run(main())
