import re
import time
import os
import sys
import subprocess
import logging
import json
import random
import string
from datetime import datetime
from urllib.parse import urlparse
import tldextract

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def extract_root_domain(url_input):
    """Extract root domain from input URL or domain"""
    # Add scheme if not present to make urlparse work properly
    if not url_input.startswith(('http://', 'https://')):
        url_input = 'https://' + url_input

    # Use tldextract to get domain and suffix (handles cases like .co.uk properly)
    extract_result = tldextract.extract(url_input)
    root_domain = f"{extract_result.domain}.{extract_result.suffix}"

    return root_domain


def create_spider_script():
    """Create the Scrapy spider script file"""
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
        'CLOSESPIDER_TIMEOUT': 300,  # 5 minute timeout
        'CLOSESPIDER_PAGECOUNT': 500,  # Limit number of pages to crawl
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
        if self.pages_visited < 500:
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

    # Create spider script file with UTF-8 encoding
    try:
        with open('spider_task.py', 'w', encoding='utf-8') as f:
            f.write(script_content.strip())
        logging.info("Created spider script file: spider_task.py")
    except Exception as e:
        logging.error(f"Error creating spider script file: {e}")


def main():
    # Get user input for URL/domain
    url_input = input("Please enter a URL or domain (e.g., 'example.com', 'www.example.com', 'https://example.com'): ")

    # Extract root domain from input
    root_domain = extract_root_domain(url_input)
    logging.info(f"Extracted root domain: {root_domain}")

    # Construct URL with https prefix
    url = f"https://{root_domain}"
    logging.info(f"Using URL: {url}")

    # Create results directory
    results_dir = "email_results"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    # Create spider script
    create_spider_script()

    # Create unique task ID and result file
    task_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    result_file = os.path.join(results_dir, f"email_results_{task_id}.json")

    # Run spider as subprocess
    logging.info(f"Starting crawler for domain: {root_domain}")
    python_executable = sys.executable
    cmd = f'{python_executable} spider_task.py "{url}" "{root_domain}" "{result_file}"'

    try:
        process = subprocess.Popen(cmd, shell=True)
        process.wait()  # Wait for process to complete

        if process.returncode != 0:
            logging.error(f"Spider task failed with exit code: {process.returncode}")
        else:
            logging.info("Spider task completed successfully.")

            # Read and display results
            if os.path.exists(result_file):
                with open(result_file, 'r', encoding='utf-8') as f:
                    result_data = json.load(f)

                emails = result_data.get('Email', [])
                if emails:
                    print("\n===== Emails Found =====")
                    for email in emails:
                        print(email)
                    print(f"\nTotal: {len(emails)} email(s)")
                    print(f"Pages visited: {result_data.get('Pages_Visited', 0)}")
                    print(f"Time used: {result_data.get('Time_Usage', 0)} seconds")
                else:
                    print("\nNo emails found on this domain.")
            else:
                logging.error(f"Result file not found: {result_file}")

    except Exception as e:
        logging.error(f"Error executing crawler: {e}")


if __name__ == "__main__":
    main()