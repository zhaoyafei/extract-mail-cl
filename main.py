from flask import Flask, request, jsonify, render_template
import os
import re
import json
import time
import random
import string
import threading
import logging
import subprocess
import sys
from urllib.parse import urlparse
import tldextract

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 初始化Flask应用
app = Flask(__name__)

# 确保结果目录存在
results_dir = "email_results"
if not os.path.exists(results_dir):
    os.makedirs(results_dir)

def extract_root_domain(url_input):
    """提取输入URL或域名的根域名"""
    # 添加协议前缀如果没有，使urlparse能正常工作
    if not url_input.startswith(('http://', 'https://')):
        url_input = 'https://' + url_input

    # 使用tldextract获取域名和后缀(正确处理.co.uk等情况)
    extract_result = tldextract.extract(url_input)
    root_domain = f"{extract_result.domain}.{extract_result.suffix}"

    return root_domain

def create_spider_script():
    """创建Scrapy爬虫脚本文件"""
    # 检查spider_task.py文件是否已存在
    if os.path.exists('spider_task.py'):
        return

    script_content = '''
import scrapy
import re
import time
import json
from scrapy.crawler import CrawlerProcess
from scrapy.linkextractors import LinkExtractor
from datetime import datetime
import logging
from scrapy.utils.log import configure_logging
from twisted.internet.error import DNSLookupError, TimeoutError, TCPTimedOutError, ConnectionRefusedError
import os
import sys

# Command line arguments: URL, DOMAIN, RESULT_FILE
if len(sys.argv) < 4:
    print("Usage: python spider_task.py URL DOMAIN RESULT_FILE")
    sys.exit(1)

url = sys.argv[1]
domain = sys.argv[2]
result_file = sys.argv[3]

# Scrapy logging configuration
configure_logging(install_root_handler=False)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)

def current_time_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

class EmailSpider(scrapy.Spider):
    name = 'email_spider'
    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'DOWNLOAD_TIMEOUT': 20,
        'RETRY_TIMES': 2,
        'HTTPPROXY_ENABLED': False,
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 110,
        },
        'LOG_LEVEL': 'INFO',
        'EXTENSIONS': {  # Disable Telnet extension
            'scrapy.extensions.telnet.TelnetConsole': None,
        },
        'CLOSESPIDER_TIMEOUT': 60,  # 1 minute timeout for API version
        'CLOSESPIDER_PAGECOUNT': 10,  # Limit number of pages to crawl for API version
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [url]
        self.allowed_domains = [domain]
        self.emails_found = set()
        self.start_time = time.time()
        self.link_extractor = LinkExtractor()
        self.result_file = result_file
        self.pages_visited = 0

    def start_requests(self):
        self.logger.info(f"Starting crawl of {self.start_urls[0]}")
        yield scrapy.Request(
            self.start_urls[0],
            callback=self.parse,
            errback=self.handle_error,
            dont_filter=True
        )

    def parse(self, response):
        self.pages_visited += 1

        # Extract emails using regex
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', response.text)
        valid_emails = []

        # Additional validation and cleaning
        for email in emails:
            # Check for valid format
            if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                # Convert to lowercase for deduplication
                valid_emails.append(email.lower())

        self.emails_found.update(valid_emails)

        if valid_emails:
            self.logger.info(f"Found {len(valid_emails)} email(s) on {response.url}")

        # Limit number of pages to crawl to avoid excessive crawling
        if self.pages_visited < 10:  # Reduced for API version
            # Extract links and follow them
            links = self.link_extractor.extract_links(response)
            for link in links:
                yield scrapy.Request(
                    url=link.url,
                    callback=self.parse,
                    errback=self.handle_error
                )

    def handle_error(self, failure):
        if failure.check(DNSLookupError):
            reason = 'dns_error'
        elif failure.check(TimeoutError, TCPTimedOutError):
            reason = 'timeout'
        elif failure.check(ConnectionRefusedError):
            reason = 'connection_refused'
        else:
            reason = 'unknown_error'
        self.logger.error(f"Error: {reason}")

    def closed(self, reason):
        end_time = time.time()
        total_time = int(end_time - self.start_time)
        now_str = current_time_str()

        if len(self.emails_found) == 0:
            status = 'no_email_found' if reason == 'finished' else reason
        else:
            status = 'success'

        # Save results to JSON file
        result_data = {
            'Start_Time': datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S'),
            'End_Time': now_str,
            'Time_Usage': total_time,
            'Email': list(self.emails_found),
            'Number_Email': len(self.emails_found),
            'Status': status,
            'Pages_Visited': self.pages_visited
        }

        try:
            with open(self.result_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False)
            print(f"Finished - Status: {status}, Emails: {len(self.emails_found)}, Pages: {self.pages_visited}, Time: {total_time}s")
        except Exception as e:
            print(f"Error saving results: {e}")
            sys.exit(1)


# Execute spider
if __name__ == '__main__':
    process = CrawlerProcess()
    process.crawl(EmailSpider)
    process.start()
'''

    # 使用UTF-8编码创建爬虫脚本文件
    try:
        with open('spider_task.py', 'w', encoding='utf-8') as f:
            f.write(script_content.strip())
        logging.info("Created spider script file: spider_task.py")
    except Exception as e:
        logging.error(f"Error creating spider script file: {e}")

def run_spider(url, domain, result_file):
    """运行爬虫作为子进程"""
    python_executable = sys.executable
    cmd = f'{python_executable} spider_task.py "{url}" "{domain}" "{result_file}"'

    try:
        process = subprocess.Popen(cmd, shell=True)
        process.wait()  # 等待进程完成
        return process.returncode == 0
    except Exception as e:
        logging.error(f"Error executing crawler: {e}")
        return False

def process_url(url_input):
    """处理URL并运行爬虫"""
    # 提取根域名
    root_domain = extract_root_domain(url_input)
    logging.info(f"Extracted root domain: {root_domain}")

    # 构造带有https前缀的URL
    url = f"https://{root_domain}"
    logging.info(f"Using URL: {url}")

    # 创建爬虫脚本(如果不存在)
    create_spider_script()

    # 创建唯一任务ID和结果文件
    task_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    result_file = os.path.join(results_dir, f"email_results_{task_id}.json")

    # 运行爬虫
    logging.info(f"Starting crawler for domain: {root_domain}")
    success = run_spider(url, root_domain, result_file)

    if success:
        logging.info("Spider task completed successfully.")
        
        # 读取结果
        if os.path.exists(result_file):
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
            
            return result_data
        else:
            logging.error(f"Result file not found: {result_file}")
            return {"error": "Result file not found"}
    else:
        logging.error("Spider task failed")
        return {"error": "Spider task failed"}

# API路由
@app.route('/api/extract-email', methods=['GET'])
def extract_email():
    url_input = request.args.get('url')
    
    if not url_input:
        return jsonify({"error": "Missing URL parameter"}), 400
    
    # 验证URL
    try:
        # 简单的URL验证
        if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-\.]+\.)+[a-zA-Z]{2,}$', extract_root_domain(url_input)):
            return jsonify({"error": "Invalid URL format"}), 400
    except Exception as e:
        return jsonify({"error": f"Invalid URL: {str(e)}"}), 400

    # 处理URL并获取结果
    result = process_url(url_input)
    
    # 返回结果
    return jsonify(result)

# 主页路由
@app.route('/')
def home():
    try:
        return render_template('index.html')
    except Exception as e:
        # 如果模板不存在，返回API信息页面
        return '''
        <html>
            <head>
                <title>Email Extractor API</title>
                <style>
                    body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                    pre { background: #f4f4f4; padding: 10px; border-radius: 5px; }
                    .example { background: #e8f5e9; padding: 10px; border-radius: 5px; margin: 10px 0; }
                </style>
            </head>
            <body>
                <h1>Email Extractor API</h1>
                <p>Extract email addresses from websites.</p>
                
                <h2>API Usage:</h2>
                <pre>/api/extract-email?url=example.com</pre>
                
                <div class="example">
                    <h3>Example:</h3>
                    <a href="/api/extract-email?url=example.com" target="_blank">/api/extract-email?url=example.com</a>
                </div>
                
                <h2>Response Format:</h2>
                <pre>{
        "Email": ["email@example.com", "another@example.com"],
        "End_Time": "2023-01-01 12:00:00",
        "Number_Email": 2,
        "Pages_Visited": 5,
        "Start_Time": "2023-01-01 11:59:00",
        "Status": "success",
        "Time_Usage": 60
    }</pre>
            </body>
        </html>
        '''

if __name__ == '__main__':
    # 创建默认的爬虫脚本
    create_spider_script()
    # 启动Flask应用
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
