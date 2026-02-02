import os
import glob
import yfinance as yf
import feedparser
from google import genai
from datetime import datetime
import re
import smtplib
from email.mime.text import MIMEText
from email.header import Header

# --- 1. 初始化配置 ---
# 从 GitHub Secrets 获取密钥
API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

# Gmail SMTP 配置
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587  # Gmail 推荐使用 587 端口配合 TLS 加密
EMAIL_USER = os.environ.get("EMAIL_USER")  # 你的 Gmail 地址
EMAIL_PASS = os.environ.get("EMAIL_PASS")  # ⚠️ 注意：这里填的是 16 位“应用专用密码”
EMAIL_TO = os.environ.get("EMAIL_TO")      # 你接收邮件的地址

# 云端知识库路径
OBSIDIAN_PATH = "./knowledge_base"

def get_china_market_data():
    """抓取核心金融数据（中国视角）"""
    print("📊 正在同步全球市场行情...")
    tickers = {
        '000001.SS': '🇨🇳 上证指数',
        '399006.SZ': '🇨🇳 创业板指',
        'CNY=X': '💱 美元/人民币',
        'GC=F': '🟡 黄金期货',
        '^TNX': '🇺🇸 10年美债',
        'BTC-USD': '🪙 比特币'
    }
    try:
        data = yf.download(list(tickers.keys()), period="7d", progress=False)
        df = data['Close'] if 'Close' in data else data
        md_table = "| 核心资产 | 最新报价 | 状态 |\n|---|---|---|\n"
        for symbol, name in tickers.items():
            series = df[symbol].dropna()
            if series.empty: continue
            price = series.iloc[-1]
            prev = series.iloc[-2] if len(series)>1 else price
            icon = "🔺" if price > prev else "💚"
            fmt = f"{price:.4f}" if "CNY" in symbol else (f"{price:.3f}%" if "^" in symbol else f"{price:.2f}")
            md_table += f"| {name} | {fmt} | {icon} |\n"
        return md_table
    except:
        return "*(暂时无法获取实时行情)*"

def get_raw_news():
    """抓取最新的国际财经新闻摘要"""
    print("🌍 正在检索国际新闻...")
    try:
        feed = feedparser.parse("https://finance.yahoo.com/news/rssindex")
        txt = ""
        for i, entry in enumerate(feed.entries[:5], 1):
            summary = re.sub('<.*?>', '', getattr(entry, 'summary', '')).strip()
            txt += f"新闻 {i}: {entry.title}\n摘要: {summary[:200]}\n\n"
        return txt
    except:
        return "*(国际新闻抓取超时)*"

def get_obsidian_knowledge():
    """读取上传的 Obsidian 笔记内容"""
    print("🧠 正在内化私人笔记逻辑...")
    knowledge_context = ""
    if not os.path.exists(OBSIDIAN_PATH):
        return "*(未发现私人笔记素材)*"
    
    files = glob.glob(os.path.join(OBSIDIAN_PATH, "*.md"))
    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                knowledge_context += f"\n【笔记素材：{os.path.basename(file_path)}】\n{content[:2000]}\n"
        except:
            pass
    return knowledge_context

def send_gmail(subject, content_md):
    """通过 Gmail 发送邮件"""
    print(f"📧 正在通过 Gmail 发送至 {EMAIL_TO}...")
    try:
        # 构造邮件
        msg = MIMEText(content_md, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_TO

        # 建立连接
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()  # 启用安全传输
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        server.quit()
        print("✅ 邮件已成功送达收件箱！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

def generate_report():
    date_str = datetime.now().strftime('%Y-%m-%d')
    market_data = get_china_market_data()
    raw_news = get_raw_news()
    my_knowledge = get_obsidian_knowledge()
    
    # 结合理财师身份的定制化 Prompt
    prompt = f"""
    今天是 {date_str}。请以资深金融策略员的身份，生成一份精简的《理财师早间内参》。

    【当前素材库】：
    1. 市场核心行情：{market_data}
    2. 全球财经头条：{raw_news}
    3. 我的投资理念/笔记：{my_knowledge}

    【任务要求】：
    1. **新闻极简汇总**：将 5 条国际新闻翻译并总结，每条不超过 50 字。增加一句针对中国市场的“文翔点评”。
    2. **内功心法**：必须显式引用【素材3】中提到的一个核心理念（如反脆弱、全天候等），以此解读当前宏观环境。
    3. **策略指南**：给出一个具体的、可执行的操作建议。

    输出语言：中文。格式：Markdown 纯文本。
    """
    
    try:
        print("🤖 Gemini 正在进行深度分析...")
        response = client.models.generate_content(model="gemini-2.5-pro", contents=prompt)
        send_gmail(f"Gemini 投资内参 ({date_str})", response.text)
    except Exception as e:
        print(f"❌ 运行过程中发生错误: {e}")

if __name__ == "__main__":
    generate_report()
