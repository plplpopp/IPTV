import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import requests
import json
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# 使用字典管理URL，更易于维护
REGION_URLS = {
    "hebei": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0iSGViZWki",
    "beijing": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0iYmVpamluZyI%3D",
    "guangdong": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0iZ3Vhbmdkb25nIg%3D%3D",
    "shanghai": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0ic2hhbmdoYWki",
    "tianjin": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0idGlhbmppbiI%3D",
    "chongqing": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0iY2hvbmdxaW5nIg%3D%3D",
    "shanxi": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0ic2hhbnhpIg%3D%3D",
    "shaanxi": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0iU2hhYW54aSI%3D",
    "liaoning": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0ibGlhb25pbmci",
    "jiangsu": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0iamlhbmdzdSI%3D",
    "zhejiang": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0iemhlamlhbmci",
    "anhui": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0i5a6J5b69Ig%3D%3D",
    "fujian": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0iRnVqaWFuIg%3D%3D",
    "jiangxi": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0i5rGf6KW%2FIg%3D%3D",
    "shandong": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0i5bGx5LicIg%3D%3D",
    "henan": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0i5rKz5Y2XIg%3D%3D",
    "hubei": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0i5rmW5YyXIg%3D%3D",
    "hunan": "https://fofa.info/result?qbase64=ImlwdHYvbGl2ZS96aF9jbi5qcyIgJiYgY291bnRyeT0iQ04iICYmIHJlZ2lvbj0i5rmW5Y2XIg%3D%3D"
}

# 备用服务器列表（如果FOFA无法访问）
BACKUP_SERVERS = [
    "http://60.214.107.42:8080",
    "http://113.57.127.43:8080", 
    "http://58.222.24.11:8080",
    "http://117.169.120.140:8080",
    "http://112.30.144.207:8080",
    "http://60.214.107.42:8080",
    "http://113.57.127.43:8080",
    "http://58.222.24.11:8080",
    "http://117.169.120.140:8080",
    "http://112.30.144.207:8080"
]

def setup_driver():
    """设置Chrome驱动"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # 添加更多选项避免检测
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        # 使用webdriver-manager自动下载和管理ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        print(f"Error setting up driver: {e}")
        raise

def clean_channel_name(name):
    """清理频道名称"""
    if not name:
        return ""
    
    # 频道名称映射表
    mappings = {
        "中央": "CCTV",
        "高清": "",
        "HD": "",
        "标清": "",
        "频道": "",
        "-": "",
        " ": "",
        "PLUS": "+",
        "(": "",
        ")": "",
        "CCTV1综合": "CCTV1",
        "CCTV2财经": "CCTV2",
        "CCTV3综艺": "CCTV3",
        "CCTV4国际": "CCTV4",
        "CCTV4中文国际": "CCTV4",
        "CCTV5体育": "CCTV5",
        "CCTV6电影": "CCTV6",
        "CCTV7军事": "CCTV7",
        "CCTV7军农": "CCTV7",
        "CCTV7国防军事": "CCTV7",
        "CCTV8电视剧": "CCTV8",
        "CCTV9记录": "CCTV9",
        "CCTV9纪录": "CCTV9",
        "CCTV10科教": "CCTV10",
        "CCTV11戏曲": "CCTV11",
        "CCTV12社会与法": "CCTV12",
        "CCTV13新闻": "CCTV13",
        "CCTV新闻": "CCTV13",
        "CCTV14少儿": "CCTV14",
        "CCTV15音乐": "CCTV15",
        "CCTV16奥林匹克": "CCTV16",
        "CCTV17农业农村": "CCTV17",
        "CCTV5+体育赛视": "CCTV5+",
        "CCTV5+体育赛事": "CCTV5+"
    }
        
    for old, new in mappings.items():
        name = name.replace(old, new)
    return name.strip()

def extract_urls_from_page(driver, url):
    """从页面提取URL"""
    try:
        print(f"🌐 Accessing FOFA: {url}")
        driver.get(url)
        
        # 等待页面加载
        time.sleep(15)  # 增加等待时间
        
        # 尝试多种选择器来找到IP地址
        selectors = [
            "//a[contains(@href, 'http://')]",
            "//span[contains(text(), 'http://')]",
            "//div[contains(text(), 'http://')]",
            "//td[contains(text(), 'http://')]",
            "//code[contains(text(), 'http://')]"
        ]
        
        page_content = driver.page_source
        print(f"📄 Page content length: {len(page_content)}")
        
        # 使用多种模式匹配IP地址
        patterns = [
            r"http://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+",
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+",
            r"ip.*\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
        ]
        
        all_urls = []
        for pattern in patterns:
            matches = re.findall(pattern, page_content, re.IGNORECASE)
            for match in matches:
                if match.startswith('http://'):
                    all_urls.append(match)
                elif ':' in match and match.count('.') == 3:
                    all_urls.append(f"http://{match}")
        
        unique_urls = list(set(all_urls))
        print(f"🔍 Found {len(unique_urls)} server URLs using regex")
        
        # 如果没找到，使用备用服务器
        if not unique_urls:
            print("⚠️ No servers found in FOFA, using backup servers")
            return BACKUP_SERVERS
        
        return unique_urls
        
    except Exception as e:
        print(f"❌ Error extracting URLs from {url}: {str(e)}")
        print("🔄 Using backup servers instead")
        return BACKUP_SERVERS

def process_single_server(url):
    """处理单个服务器"""
    results = []
    try:
        # 尝试多种可能的JSON路径
        json_paths = [
            "/iptv/live/1000.json?key=txiptv",
            "/iptv/live/1000.json",
            "/live/1000.json",
            "/tv/1000.json",
            "/iptv/live.json"
        ]
        
        for json_path in json_paths:
            try:
                json_url = f"{url}{json_path}"
                print(f"📡 Trying: {json_url}")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/json, text/plain, */*',
                    'Referer': url
                }
                
                response = requests.get(json_url, timeout=8, headers=headers)
                if response.status_code == 200:
                    json_data = response.json()
                    
                    channel_count = 0
                    for item in json_data.get('data', []):
                        if isinstance(item, dict):
                            name = item.get('name')
                            urlx = item.get('url')
                            
                            if name and urlx:
                                cleaned_name = clean_channel_name(name)
                                # 确保URL是完整的
                                if urlx.startswith('/'):
                                    full_url = f"{url}{urlx}"
                                else:
                                    full_url = f"{url}/{urlx}"
                                results.append(f"{cleaned_name},{full_url}")
                                channel_count += 1
                    
                    print(f"✅ Found {channel_count} channels from {url} using {json_path}")
                    break  # 找到有效路径就停止尝试
                    
            except Exception as e:
                continue  # 尝试下一个路径
                
        if not results:
            print(f"❌ No channels found from {url}")
                    
    except Exception as e:
        print(f"❌ Error processing server {url}: {str(e)}")
    
    return results

def process_region(region_name, url):
    """处理单个地区"""
    print(f"\n{'='*60}")
    print(f"🏁 Processing {region_name.upper()}")
    print(f"{'='*60}")
    
    driver = setup_driver()
    try:
        # 提取服务器URL
        server_urls = extract_urls_from_page(driver, url)
        print(f"📡 Found {len(server_urls)} servers for {region_name}")
        
        if not server_urls:
            print(f"⚠️ No servers available for {region_name}")
            return []
        
        # 处理服务器
        all_results = []
        success_count = 0
        
        for i, server_url in enumerate(server_urls[:8]):  # 限制处理数量
            try:
                print(f"🔄 [{i+1}/{len(server_urls[:8])}] Processing {server_url}")
                results = process_single_server(server_url)
                if results:
                    all_results.extend(results)
                    success_count += 1
                    print(f"✅ Successfully got {len(results)} channels from {server_url}")
                time.sleep(1)  # 请求间隔
            except Exception as e:
                print(f"❌ Failed to process {server_url}: {e}")
                continue
        
        # 去重
        unique_results = list(set(all_results))
        print(f"📊 {region_name}: {len(unique_results)} unique channels from {success_count} servers")
        return unique_results
        
    except Exception as e:
        print(f"❌ Error processing region {region_name}: {str(e)}")
        return []
    finally:
        if driver:
            driver.quit()

def save_results(results, filename):
    """保存结果到文件"""
    if not results:
        print(f"⚠️ No results to save for {filename}")
        return False
    
    # 按频道名称排序
    sorted_results = sorted(results, key=lambda x: x.split(',')[0])
    
    with open(filename, "w", encoding="utf-8") as file:
        for result in sorted_results:
            file.write(result + "\n")
    print(f"💾 Saved {len(sorted_results)} results to {filename}")
    return True

def main():
    """主函数"""
    print("🚀 Starting IPTV collection process...")
    start_time = time.time()
    
    all_files = []
    successful_regions = 0
    
    # 处理所有地区
    for region_name, url in REGION_URLS.items():
        try:
            results = process_region(region_name, url)
            filename = f"{region_name}.txt"
            if save_results(results, filename):
                all_files.append(filename)
                successful_regions += 1
            time.sleep(3)  # 地区间延迟
        except Exception as e:
            print(f"❌ Failed to process {region_name}: {e}")
            continue
    
    # 合并文件
    print(f"\n{'='*60}")
    print("🔄 Merging regional files...")
    print(f"{'='*60}")
    
    if all_files:
        # 合并并去重
        all_channels = set()
        for file in all_files:
            if os.path.exists(file):
                with open(file, 'r', encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            all_channels.add(line)
        
        # 保存合并文件
        sorted_channels = sorted(list(all_channels))
        with open("IPTV.txt", "w", encoding="utf-8") as f:
            f.write('\n'.join(sorted_channels))
        
        print(f"✅ Merged {len(all_files)} files into IPTV.txt")
        print(f"📺 Total unique channels: {len(sorted_channels)}")
    else:
        print("❌ No valid files to merge")
        # 创建空的IPTV.txt文件
        with open("IPTV.txt", "w", encoding="utf-8") as f:
            f.write("")
    
    # 统计信息
    end_time = time.time()
    processing_time = end_time - start_time
    
    print(f"\n{'='*60}")
    print("📊 COLLECTION SUMMARY")
    print(f"{'='*60}")
    print(f"✅ Successful regions: {successful_regions}/{len(REGION_URLS)}")
    print(f"⏱️  Processing time: {processing_time:.2f} seconds")
    
    if os.path.exists("IPTV.txt"):
        with open("IPTV.txt", "r", encoding="utf-8") as f:
            total_channels = len(f.readlines())
        print(f"📺 Total channels collected: {total_channels}")
    else:
        print("📺 Total channels collected: 0")
    
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
