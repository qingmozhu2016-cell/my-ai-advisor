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

# 邮箱配置
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = os.environ.get("EMAIL_USER", "").strip()
EMAIL_PASS = os.environ.get("EMAIL_PASS", "").strip()
EMAIL_TO = os.environ.get("EMAIL_TO", "").strip()

# 路径配置
OBSIDIAN_PATH = "./knowledge_base"
REPORT_DIR = "./AI_Reports"

def get_market_data():
    """第一部分：核心指数 + 黄金/比特币"""
    print("📊 正在获取全球核心资产数据...")
    tickers = {
        '000001.SS': '🇨🇳 上证指数',
        '399006.SZ': '🇨🇳 创业板指',
        'CNY=X': '💱 美元/人民币', 
        'FXI': '🇨🇳 A50 (ETF)',
        '^TNX': '🇺🇸 10年美债',
        'GC=F': '🟡 黄金期货',
        'BTC-USD': '🪙 比特币'
    }
    
    try:
        data = yf.download(list(tickers.keys()), period="5d", progress=False)
        df = data['Close'] if 'Close' in data else data
        
        md_table = "| 资产 | 最新价 | 涨跌 |\n|---|---|---|\n"
        for symbol, name in tickers.items():
            try:
                # 强制去空值，取最近有效交易日
                series = df[symbol].dropna()
                if series.empty: continue
                
                price = series.iloc[-1]
                prev = series.iloc[-2] if len(series) > 1 else price
                
                # 计算涨跌幅
                pct_change = ((price - prev) / prev) * 100
                icon = "🔺" if pct_change > 0 else "💚"
                
                # 格式化
                if "CNY" in symbol: fmt = f"{price:.4f}"
                elif "^" in symbol: fmt = f"{price:.3f}%"
                else: fmt = f"{price:.2f}"
                
                md_table += f"| {name} | {fmt} | {icon} {pct_change:+.2f}% |\n"
            except: pass
        return md_table
    except: return "*(行情数据暂时不可用)*"

def get_news_brief():
    """第二部分：获取新闻素材 (为AI提供筛选池)"""
    print("🌍 正在聚合关键财经新闻...")
    news_list = []
    
    # 源配置：中西合璧
    sources = [
        {"name": "联合早报", "url": "https://www.zaobao.com.sg/rss/finance.xml"},
        {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"}
    ]
    
    for src in sources:
        try:
            feed = feedparser.parse(src["url"])
            if not feed.entries: continue
            
            # 每个源抓取前 5 条作为“候选池”，让 AI 从中优中选优
            for entry in feed.entries[:5]:
                clean_summary = re.sub('<.*?>', '', getattr(entry, 'summary', '')).strip()
                news_list.append(f"【{src['name']}】{entry.title} - {clean_summary[:100]}")
        except: pass
    
    return "\n".join(news_list)

def get_obsidian_knowledge():
    """读取知识库"""
    context = ""
    if os.path.exists(OBSIDIAN_PATH):
        for f in glob.glob(os.path.join(OBSIDIAN_PATH, "*.md")):
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    context += f"\n【笔记：{os.path.basename(f)}】\n{file.read()[:2000]}\n"
            except: pass
    return context

def save_and_send(title, content):
    """保存到仓库文件并发送邮件"""
    
    # 1. 保存文件 (同步回 Obsidian)
    if not os.path.exists(REPORT_DIR):
        os.makedirs(REPORT_DIR)
    
    filename = f"{REPORT_DIR}/{datetime.now().strftime('%Y-%m-%d')}_AI_Daily.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 日报已保存至: {filename}")

    # 2. 发送邮件
    if not EMAIL_USER: return
    
    msg = MIMEText(content, 'plain', 'utf-8')
    msg['Subject'] = title
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
        print(f"❌ 邮件发送失败: {e}")

def generate_report():
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    market = get_market_data()
    news = get_news_brief()
    knowledge = get_obsidian_knowledge()
    
    print("🤖 Gemini 2.5 Pro 正在生成精简策略...")
    
    prompt = f"""
    【角色】朱文翔（资深理财经理，关注家庭风控）。
    【日期】{date_str}
    
    【任务】生成《家庭财富风险管理日报》，Markdown格式。
    
    【输入素材】
    1. 行情：\n{market}
    2. 新闻候选池（请严格筛选，去粗取精）：\n{news}
    3. 你的笔记库：\n{knowledge}
    
    【文章结构要求】
    
    **第一部分：核心资产看板**
    - 直接展示行情表格。
    - 用一句话犀利点评比特币和黄金的最新走势。
    
    **第二部分：财经要闻速递（Top 5）**
    - **严格筛选**：从新闻池中仅挑选 **5条** 对中国家庭财富影响最大的新闻。
    - 格式：`1. [新闻标题]`
    - 点评：`> 💡 影响分析：...` (一针见血指出对理财/房产/股市的具体影响)。
    
    **第三部分：深度策略与行动**
    - **聚焦**：基于上述 Top 5 新闻中的核心事件。
    - **观点**：结合你的专业经验进行深度点评。**如果笔记库中有相关的反脆弱/全天候理论，请自然引用（不必强求，有则引，无则结合通用理财逻辑）。**
    - **行动**：给出 1 条具体的家庭资产配置建议（如：买入、观望、置换美元等）。
    """
    
    try:
        # 使用 Pro 模型确保筛选质量
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt
        )
        
        if response.text:
            save_and_send(f"【AI日报】{date_str} 精选策略 (Top 5)", response.text)
        else:
            print("❌ 生成内容为空")
            
    except Exception as e:
        print(f"❌ 运行报错: {e}")

if __name__ == "__main__":
    generate_report()
