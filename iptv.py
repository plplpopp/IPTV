import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
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

# 频道名称映射表
CHANNEL_NAME_MAPPING = {
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
    
    # 使用系统安装的ChromeDriver
    service = Service('/usr/local/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def clean_channel_name(name):
    """清理频道名称"""
    if not name:
        return ""
        
    for old, new in CHANNEL_NAME_MAPPING.items():
        name = name.replace(old, new)
    return name.strip()

def extract_urls_from_page(driver, url, wait_time=10):
    """从页面提取URL"""
    try:
        print(f"Extracting URLs from: {url}")
        driver.get(url)
        time.sleep(wait_time)
        page_content = driver.page_source
        
        pattern = r"http://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+"
        urls_all = re.findall(pattern, page_content)
        unique_urls = list(set(urls_all))
        print(f"Found {len(unique_urls)} unique server URLs")
        return unique_urls
    except Exception as e:
        print(f"Error extracting URLs from {url}: {str(e)}")
        return []

def process_single_server(url):
    """处理单个服务器"""
    results = []
    try:
        json_url = f"{url}/iptv/live/1000.json?key=txiptv"
        print(f"Fetching JSON from: {json_url}")
        
        response = requests.get(json_url, timeout=10)
        response.raise_for_status()
        json_data = response.json()

        channel_count = 0
        for item in json_data.get('data', []):
            if isinstance(item, dict):
                name = item.get('name')
                urlx = item.get('url')
                
                if name and urlx:
                    cleaned_name = clean_channel_name(name)
                    full_url = f"{url}{urlx}"
                    results.append(f"{cleaned_name},{full_url}")
                    channel_count += 1
        
        print(f"Found {channel_count} channels from {url}")
        return results
                    
    except requests.exceptions.RequestException as e:
        print(f"Request failed for {url}: {str(e)}")
    except json.JSONDecodeError as e:
        print(f"JSON decode error for {url}: {str(e)}")
    except Exception as e:
        print(f"Unexpected error for {url}: {str(e)}")
    
    return results

def process_region(region_name, url, max_workers=5):
    """处理单个地区"""
    print(f"\n{'='*50}")
    print(f"Processing {region_name}...")
    print(f"{'='*50}")
    
    driver = setup_driver()
    try:
        # 提取服务器URL
        server_urls = extract_urls_from_page(driver, url)
        print(f"Found {len(server_urls)} servers in {region_name}")
        
        if not server_urls:
            print(f"No servers found for {region_name}")
            return []
        
        # 使用多线程处理服务器
        all_results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(process_single_server, server_url): server_url 
                for server_url in server_urls[:20]  # 限制处理前20个服务器避免超时
            }
            
            completed_count = 0
            for future in as_completed(future_to_url):
                server_url = future_to_url[future]
                completed_count += 1
                try:
                    results = future.result()
                    all_results.extend(results)
                    print(f"[{completed_count}/{len(future_to_url)}] Processed {server_url}: {len(results)} channels")
                except Exception as e:
                    print(f"[{completed_count}/{len(future_to_url)}] Error processing {server_url}: {str(e)}")
        
        # 去重
        unique_results = list(set(all_results))
        print(f"Region {region_name}: {len(unique_results)} unique channels collected")
        return unique_results
        
    except Exception as e:
        print(f"Error processing region {region_name}: {str(e)}")
        return []
    finally:
        driver.quit()

def save_results(results, filename):
    """保存结果到文件"""
    if not results:
        print(f"No results to save for {filename}")
        return
    
    # 按频道名称排序
    sorted_results = sorted(results, key=lambda x: x.split(',')[0])
    
    with open(filename, "w", encoding="utf-8") as file:
        for result in sorted_results:
            file.write(result + "\n")
    print(f"Saved {len(sorted_results)} results to {filename}")

def merge_files(file_paths, output_file="IPTV.txt"):
    """合并多个文件"""
    valid_contents = []
    total_channels = 0
    
    for file_path in file_paths:
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, 'r', encoding="utf-8") as file:
                content = file.read().strip()
                if content:
                    valid_contents.append(content)
                    channel_count = len(content.strip().split('\n'))
                    total_channels += channel_count
                    print(f"Added {channel_count} channels from {file_path}")
    
    if valid_contents:
        # 合并并去重
        all_lines = []
        for content in valid_contents:
            all_lines.extend(content.split('\n'))
        
        unique_lines = sorted(list(set(all_lines)))
        
        with open(output_file, "w", encoding="utf-8") as output:
            output.write('\n'.join(unique_lines))
        
        print(f"Merged {len(valid_contents)} files into {output_file}")
        print(f"Total unique channels: {len(unique_lines)}")
    else:
        print("No valid content to merge")

def main():
    """主函数"""
    print("🚀 Starting IPTV collection process...")
    start_time = time.time()
    all_files = []
    
    # 处理所有地区
    for region_name, url in REGION_URLS.items():
        try:
            results = process_region(region_name, url)
            filename = f"{region_name}.txt"
            save_results(results, filename)
            all_files.append(filename)
            time.sleep(2)  # 地区间延迟
        except Exception as e:
            print(f"Error processing region {region_name}: {str(e)}")
            continue
    
    # 合并文件
    print(f"\n{'='*50}")
    print("Merging all regional files...")
    print(f"{'='*50}")
    merge_files(all_files)
    
    # 统计信息
    total_channels = 0
    regional_stats = []
    for file in all_files:
        if os.path.exists(file):
            with open(file, 'r', encoding="utf-8") as f:
                lines = f.readlines()
                channel_count = len(lines)
                total_channels += channel_count
                regional_stats.append(f"{file}: {channel_count} channels")
    
    end_time = time.time()
    processing_time = end_time - start_time
    
    print(f"\n{'='*50}")
    print("📊 COLLECTION SUMMARY")
    print(f"{'='*50}")
    for stat in regional_stats:
        print(f"  {stat}")
    print(f"{'='*50}")
    print(f"⏱️  Processing completed in {processing_time:.2f} seconds")
    print(f"📺 Total channels collected: {total_channels}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
