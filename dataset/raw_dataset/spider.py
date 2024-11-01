from multiprocessing import Process
from urllib.parse import urlparse
import scrapy
import json
import html2text
from bs4 import BeautifulSoup
import os
import time
import threading
from twisted.internet import reactor
from dataset.raw_dataset.clean_document import clean_document

# Define a global variable to track the last crawl time
last_crawl_time = time.time()
timeout = 60  # 1 minute
signals = scrapy.signals


def watchdog():
    """
    This function will monitor the crawling process and restart the spider if no new crawl occurs within the timeout period.
    """
    global last_crawl_time
    while True:
        time_since_last_crawl = time.time() - last_crawl_time
        
        if time_since_last_crawl > timeout:
            print(f"No activity for {timeout} seconds. Restarting the crawler process...")
            time.sleep(1)  # Wait for 5 seconds before restarting the crawl
            reactor.stop()  # Stop the current Twisted reactor (which stops the crawl)
            break  # Exit the watchdog loop and start a new crawl

        time.sleep(1)  # Check every 5 seconds



class DomainSpider(scrapy.Spider):
    name = "domain_spider"
    start_urls = [
        "https://www.healthline.com/",
        "https://www.cdc.gov/",
        "https://www.who.int/",
        "https://www.npr.org/sections/health/",
        "https://www.ama-assn.org/",
        "https://www.nih.gov/",
        "https://www.mayoclinic.org/",
        "https://www.webmd.com/",
        "https://www.hopkinsmedicine.org/",
        "https://www.ncbi.nlm.nih.gov/",
        "https://medlineplus.gov/",
        "https://jamanetwork.com/",
        "https://www.nejm.org/",
        "https://www.healthgrades.com/",
        "https://www.medicinenet.com/",
        "https://www.medscape.com/",
        "https://www.medicalnewstoday.com/",
        "https://www.drugs.com/",
        "https://www.everydayhealth.com/"
    ]
    visited_urls_file = "dataset/raw_dataset/scraper/visited_urls.txt"
    data_file = "dataset/raw_dataset/scraper/extracted_text.json"
    linked_domains_file = "dataset/raw_dataset/scraper/linked_domains.txt"
    interval = 60  # 1 minute

    def __init__(self, *args, **kwargs):
        super(DomainSpider, self).__init__(*args, **kwargs)
        self.visited_urls = self.load_visited_urls()
        self.linked_domains = self.load_linked_domains()
        self.start_time = time.time()
        self.file_lock = threading.Lock()
        self.current_file = self.get_new_file()

    def load_visited_urls(self):
        if os.path.exists(self.visited_urls_file):
            with open(self.visited_urls_file, "r") as f:
                return set(f.read().splitlines())
        return set()

    def load_linked_domains(self):
        if os.path.exists(self.linked_domains_file):
            with open(self.linked_domains_file, "r") as f:
                return set(f.read().splitlines())
        return set()

    def get_new_file(self):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        new_file = f"dataset/raw_dataset/scraper/extracted_text_{timestamp}.json"
        with open(new_file, "w") as f:
            f.write("[\n")
        return new_file

    def parse(self, response):
        global last_crawl_time
        last_crawl_time = time.time() 
        document_transformer = html2text.HTML2Text()
        document_transformer.ignore_links = True
        document_transformer.ignore_images = True
        continue_crawl = True
        title = ""
        locale = ""
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string
            locale = soup.html.get("lang")
            main_content = soup.body
        except Exception:
            continue_crawl = False
        try:
            if locale != "en":
                continue_crawl = False
        except Exception:
            pass
        links = response.css('a::attr(href)').getall()
        # remove links which include [facebook, twitter, instagram, linkedin, youtube, pinterest, snapchat, reddit, google, amazon, microsoft, apple, wikipedia]
        link_list = [response.urljoin(link) for link in links]
        filtered_links = []
        for link in link_list:
            if not any(social_media in link for social_media in [
                "facebook", "twitter", "instagram", "linkedin", "youtube",
                "pinterest", "snapchat", "reddit", "google", "amazon",
                "microsoft", "apple", "wikipedia", "tiktok", "adobe.com",
                "onetrust", "zoom", "youtu.be", "trello", "slack", "github",
                "bit.ly", "tinyurl", "ow.ly", "buff.ly", "dlvr.it", "ift.tt",
                "feedburner", "feedblitz", "feedproxy", "feedly", "mailchimp",
                "constantcontact", "aweber", "getresponse", "sendgrid",
                "sendinblue", "mailgun", "mailerlite", "moosend", "convertkit",
                "drip", "activecampaign", "hubspot", "salesforce", "zoho", "tel:"
            ]):
                filtered_links.append(link)
        link_list = filtered_links
        if continue_crawl:
            try:
                for tag in main_content.find_all(['header', 'footer']):
                    tag.decompose()
            except Exception:
                pass
            document = document_transformer.handle(str(main_content))
            document = clean_document(document)
            parsed_url = urlparse(response.url)
            domain_parts = parsed_url.netloc.split('.')
            if len(domain_parts) >= 2:
                toplevel_domain = '.'.join(domain_parts[-2:])
            else:
                toplevel_domain = parsed_url.netloc
            link_list_without_same_domain = [link for link in link_list if toplevel_domain not in link]
            if len(document) > 100:
                data_entry = {
                    "url": response.url,
                    "text": document,
                    "domain": toplevel_domain,
                    "links": link_list_without_same_domain,
                    "title": title
                }
                if link_list_without_same_domain:
                    for link in link_list_without_same_domain:
                        domain_parts = urlparse(link).netloc.split('.')
                        if len(domain_parts) >= 2:
                            linked_toplevel_domain = '.'.join(domain_parts[-2:])
                        else:
                            linked_toplevel_domain = urlparse(link).netloc
                        if linked_toplevel_domain not in self.linked_domains:
                            self.linked_domains.add(linked_toplevel_domain)
                            self.save_linked_domain(linked_toplevel_domain)
            self.write_to_file(data_entry)

        # Append the current URL to the visited set and file
        # self.load_visited_urls()
        self.visited_urls.add(response.url)
        self.save_visited_url(response.url)

        # Check if it's time to create a new file
        if time.time() - self.start_time >= self.interval:
            self.close()
            self.current_file = self.get_new_file()
            self.start_time = time.time()

        # Extract and follow links
        for full_url in link_list:
            if full_url not in self.visited_urls and self.is_valid_url(full_url) and not full_url.endswith(('.png', '.jpg', '.svg', '.pdf')):
                yield scrapy.Request(full_url, callback=self.parse)

    def write_to_file(self, data_entry):
        with self.file_lock, open(self.current_file, "a") as f:
            f.write(json.dumps(data_entry) + ",\n")

    def save_visited_url(self, url):
        with open(self.visited_urls_file, "a") as f:
            f.write(url + "\n")

    def save_linked_domain(self, domain):
        with open(self.linked_domains_file, "a") as f:
            f.write(domain + "\n")

    def is_valid_url(self, url):
        return any(url.startswith(prefix) for prefix in self.start_urls)

    def close(self):
        with open(self.current_file, "r+") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() > 0:
                f.seek(f.tell() - 2, os.SEEK_SET)
                last_char = f.read(1)
                if last_char == ",":
                    f.seek(f.tell() - 1, os.SEEK_SET)
                    f.truncate()
            f.write("\n]")

    def closed(self, reason):
        self.close()


def on_spider_idle():
    """
    Signal handler to detect when the spider becomes idle (stuck).
    """
    global last_crawl_time
    last_crawl_time = time.time()  # Update the last crawl time on spider idle
    print("Spider is idle. Last activity time updated.")


def run_spider():
    """
    Function to run the spider with a timeout mechanism.
    """
    global last_crawl_time
    process = CrawlerProcess()

    # Attach signal handlers
    process.crawl(DomainSpider)
    
    # Connect a signal handler to the spider idle signal to keep track of activity
    crawler = list(process.crawlers)[0]
    crawler.signals.connect(on_spider_idle, signal=signals.spider_idle)
    
    # Start the crawling process
    threading.Thread(target=watchdog, daemon=True).start()  # Run the watchdog in a separate thread
    process.start()  # This will block until the reactor stops


def start_spider_process():
    p = Process(target=run_spider)
    p.start()
    p.join()
    p2 = Process(target=run_spider)
    p2.start()
    p2.join()
    p3 = Process(target=run_spider)
    p3.start()
    p3.join()


if __name__ == "__main__":
    from scrapy.crawler import CrawlerProcess
    while True:
        last_crawl_time = time.time()
        start_spider_process()
        # process = CrawlerProcess()
        # process.crawl(DomainSpider)
        # process.start()
