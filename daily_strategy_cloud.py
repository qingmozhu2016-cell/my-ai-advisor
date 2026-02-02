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

# --- 1. 配置 (云端版去掉代理) ---
# os.environ['https_proxy'] ... (删掉！)
# os.environ['http_proxy'] ... (删掉！)

# 从环境变量获取密钥 (GitHub Secrets)
API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

# 邮箱配置 (请在 GitHub Secrets 里配置，不要写明文)
SMTP_SERVER = "smtp.qq.com" # 举例用QQ邮箱，如果是Gmail则不同
SMTP_PORT = 465
EMAIL_USER = os.environ.get("EMAIL_USER")     # 发件人邮箱
EMAIL_PASS = os.environ.get("EMAIL_PASS")     # 邮箱授权码
EMAIL_TO = os.environ.get("EMAIL_TO")         # 收件人邮箱

# 路径改为相对路径 (因为云端不知道你的 Mac 路径)
OBSIDIAN_PATH = "./knowledge_base"

def get_china_market_data():
    # ... (保持原样，省略代码以节省篇幅，逻辑不变) ...
    # 记得把之前的 get_china_market_data 函数内容复制过来
    return "| A股 | 演示数据 | 🔺 |\n" # 这里简写了，请填入完整逻辑

def get_raw_news():
    # ... (保持原样) ...
    return "News..."

def get_obsidian_knowledge():
    print(f"📚 正在连接云端知识库: {OBSIDIAN_PATH} ...")
    knowledge_context = ""
    if not os.path.exists(OBSIDIAN_PATH):
        return "*(云端未找到知识库文件夹)*"
    
    # 扫描目录下所有 .md
    files = glob.glob(os.path.join(OBSIDIAN_PATH, "*.md"))
    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                knowledge_context += f"\n【笔记】\n{f.read()[:3000]}\n"
        except: pass
    return knowledge_context

def send_email(subject, content_md):
    """发送邮件函数"""
    print("📧 正在发送邮件...")
    msg = MIMEText(content_md, 'markdown', 'utf-8') # 注意：手机邮件客户端可能不完全支持Markdown渲染
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_TO

    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        server.quit()
        print("✅ 邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

def generate_report():
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    # 获取数据
    market_data = get_china_market_data() # 请确保把之前的完整函数放进来
    raw_news = get_raw_news()             # 同上
    my_knowledge = get_obsidian_knowledge()
    
    print("🧠 Gemini 正在思考...")
    try:
        prompt = f"""
        今天是 {date_str}。
        【素材1】{market_data}
        【素材2】{raw_news}
        【素材3】{my_knowledge}
        请生成一份《A股策略内参》，Markdown格式，800字。
        """
        
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt
        )
        
        # 发送邮件
        send_email(f"Gemini 投资内参 ({date_str})", response.text)
        
    except Exception as e:
        print(f"❌ 运行出错: {e}")

if __name__ == "__main__":
    generate_report()