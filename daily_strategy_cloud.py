import os
import glob
import yfinance as yf
import feedparser
from google import genai
from datetime import datetime
import re
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

# --- 1. 基础配置 ---
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
client = genai.Client(api_key=API_KEY)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = os.environ.get("EMAIL_USER", "").strip()
EMAIL_PASS = os.environ.get("EMAIL_PASS", "").strip()
EMAIL_TO = os.environ.get("EMAIL_TO", "").strip()

OBSIDIAN_PATH = "./knowledge_base"

def get_china_market_data():
    """获取核心资产行情"""
    print("📊 正在同步核心资产行情...")
    tickers = {
        '000001.SS': '🇨🇳 上证指数',
        '399006.SZ': '🇨🇳 创业板指',
        'CNY=X': '💱 美元/人民币', 
        'FXI': '🇨🇳 中国A50 (ETF代理)', 
        '^TNX': '🇺🇸 10年美债',
        'GC=F': '🟡 黄金期货'
    }
    try:
        data = yf.download(list(tickers.keys()), period="7d", progress=False)
        df = data['Close'] if 'Close' in data else data
        md_table = "| 核心资产 | 最新报价 | 趋势 |\n|---|---|---|\n"
        for symbol, name in tickers.items():
            try:
                series = df[symbol].dropna()
                if series.empty: continue
                price = series.iloc[-1]
                prev = series.iloc[-2] if len(series) > 1 else price
                icon = "🔺" if price > prev else "💚"
                fmt = f"{price:.4f}" if "CNY" in symbol else (f"{price:.3f}%" if "^" in symbol else f"{price:.2f}")
                md_table += f"| {name} | {fmt} | {icon} |\n"
            except: pass
        return md_table
    except: return "*(行情接口暂时波动)*"

def get_news_brief():
    """获取新闻"""
    print("🌍 正在聚合双语财经新闻...")
    news_content = ""
    sources = [
        {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
        {"name": "联合早报", "url": "https://www.zaobao.com.sg/rss/finance.xml"}
    ]
    for src in sources:
        try:
            feed = feedparser.parse(src["url"])
            if not feed.entries: continue
            news_content += f"\n**【{src['name']}】**\n"
            for i, entry in enumerate(feed.entries[:3], 1):
                clean_summary = re.sub('<.*?>', '', getattr(entry, 'summary', '')).strip()
                news_content += f"{i}. {entry.title}\n"
        except: pass
    return news_content

def get_obsidian_knowledge():
    """读取私人笔记"""
    print("🧠 正在加载知识库...")
    context = ""
    if os.path.exists(OBSIDIAN_PATH):
        files = glob.glob(os.path.join(OBSIDIAN_PATH, "*.md"))
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    context += f"\n【参考笔记：{os.path.basename(f)}】\n{file.read()[:2000]}\n"
            except: pass
    return context

def send_gmail(subject, content):
    """发送邮件 (已修复格式问题)"""
    if not EMAIL_USER: return

    # ⚠️ 关键修复：将 'markdown' 改为 'plain'
    # 这样手机和网页端才能正确把 Markdown 当作纯文本显示出来
    msg = MIMEText(content, 'plain', 'utf-8') 
    
    msg['Subject'] = subject
    msg['From'] = formataddr(("朱文翔的AI助理", EMAIL_USER))
    msg['To'] = EMAIL_TO

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        server.quit()
        print("✅ 邮件已发送！")
    except Exception as e:
        print(f"❌ 发送失败: {e}")

def generate_report():
    date_str = datetime.now().strftime('%Y-%m-%d')
    market = get_china_market_data()
    news = get_news_brief()
    knowledge = get_obsidian_knowledge()
    
    print("🤖 Gemini 正在思考...")
    
    prompt = f"""
    【角色】朱文翔（资深保险理财师，信奉反脆弱与全天候策略）。
    【日期】{date_str}
    【素材】
    1. 行情：{market}
    2. 新闻：{news}
    3. 笔记：{knowledge}
    
    【任务】
    写一份《家庭财富风险管理日报》（Markdown格式，600字）。
    1. 点评中国资产表现。
    2. 提炼1条关键新闻并点评。
    3. 引用笔记中的观点，给出一个具体操作建议。
    """
    
    try:
        # ⚠️ 稳妥起见，改用 gemini-2.0-flash，速度快且稳定
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=prompt
        )
        
        # ⚠️ 增加空内容检查
        if response.text:
            print(f"📝 生成成功！字数：{len(response.text)}")
            send_gmail(f"【内参】家庭财富日报 ({date_str})", response.text)
        else:
            print("❌ 生成内容为空！")
            send_gmail("【报错】今日生成失败", "Gemini 返回了空内容，请检查日志。")
            
    except Exception as e:
        print(f"❌ 运行报错: {e}")
        send_gmail("【报错】脚本运行出错", str(e))

if __name__ == "__main__":
    generate_report()
