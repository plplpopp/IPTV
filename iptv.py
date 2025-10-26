import time
import requests
import json
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('iptv_collector.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 主服务器列表
MAIN_SERVERS = [
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

# 配置常量
CONFIG = {
    'timeout': 8,
    'max_workers': 10,
    'request_delay': 0.5
}

class IPTVCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Connection': 'keep-alive'
        })

    def clean_channel_name(self, name):
        """清理频道名称"""
        if not name:
            return ""
        
        # 频道名称映射表
        name_mappings = {
            r"中央(\d+)": r"CCTV\1",
            r"CCTV-?(\d+)": r"CCTV\1",
            r"高清": "",
            r"HD": "",
            r"超清": "",
            r"标清": "",
            r"频道": "",
            r"台": "",
            r"[-_\s]": "",
            r"PLUS": "+",
            r"[()（）]": "",
            r"CCTV1综合": "CCTV1",
            r"CCTV2财经": "CCTV2",
            r"CCTV3综艺": "CCTV3",
            r"CCTV4中文国际": "CCTV4",
            r"CCTV4国际": "CCTV4",
            r"CCTV5体育": "CCTV5",
            r"CCTV6电影": "CCTV6",
            r"CCTV7军事": "CCTV7",
            r"CCTV7军农": "CCTV7",
            r"CCTV7国防军事": "CCTV7",
            r"CCTV8电视剧": "CCTV8",
            r"CCTV9记录": "CCTV9",
            r"CCTV9纪录": "CCTV9",
            r"CCTV10科教": "CCTV10",
            r"CCTV11戏曲": "CCTV11",
            r"CCTV12社会与法": "CCTV12",
            r"CCTV13新闻": "CCTV13",
            r"CCTV新闻": "CCTV13",
            r"CCTV14少儿": "CCTV14",
            r"CCTV15音乐": "CCTV15",
            r"CCTV16奥林匹克": "CCTV16",
            r"CCTV17农业农村": "CCTV17",
            r"CCTV5\+体育赛视": "CCTV5+",
            r"CCTV5\+体育赛事": "CCTV5+"
        }
        
        cleaned_name = str(name)
        for pattern, replacement in name_mappings.items():
            cleaned_name = re.sub(pattern, replacement, cleaned_name)
        
        return cleaned_name.strip()

    def is_valid_url(self, url):
        """验证URL是否有效"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

    def test_channel_quality(self, channel_url):
        """测试频道质量"""
        try:
            start_time = time.time()
            response = self.session.head(channel_url, timeout=5, allow_redirects=True)
            response_time = time.time() - start_time
            
            if response.status_code in [200, 302]:
                return True, response_time
            return False, response_time
        except:
            return False, float('inf')

    def process_single_server(self, server_url):
        """处理单个服务器"""
        results = []
        try:
            # 可能的JSON路径列表
            json_paths = [
                "/iptv/live/1000.json?key=txiptv",
                "/iptv/live/1000.json",
                "/live/1000.json",
                "/tv/1000.json",
                "/iptv/live.json",
                "/api/live",
                "/live.json"
            ]
            
            for json_path in json_paths:
                try:
                    # 构建完整的JSON URL
                    if json_path.startswith('/'):
                        json_url = f"{server_url}{json_path}"
                    else:
                        json_url = f"{server_url}/{json_path}"
                    
                    logging.info(f"Trying: {json_url}")
                    
                    response = self.session.get(json_url, timeout=CONFIG['timeout'])
                    if response.status_code == 200:
                        try:
                            json_data = response.json()
                        except json.JSONDecodeError:
                            logging.warning(f"Invalid JSON from {json_url}")
                            continue
                        
                        channel_count = 0
                        # 处理不同的JSON结构
                        data_list = json_data.get('data', [])
                        if not data_list and isinstance(json_data, list):
                            data_list = json_data
                        
                        for item in data_list:
                            if isinstance(item, dict):
                                name = item.get('name', '') or item.get('title', '')
                                urlx = item.get('url', '') or item.get('link', '')
                                
                                if name and urlx:
                                    cleaned_name = self.clean_channel_name(name)
                                    
                                    # 构建完整的频道URL
                                    if urlx.startswith(('http://', 'https://')):
                                        full_url = urlx
                                    elif urlx.startswith('/'):
                                        full_url = f"{server_url}{urlx}"
                                    else:
                                        full_url = f"{server_url}/{urlx}"
                                    
                                    if self.is_valid_url(full_url):
                                        # 测试频道可用性
                                        is_available, response_time = self.test_channel_quality(full_url)
                                        if is_available:
                                            results.append({
                                                'name': cleaned_name,
                                                'url': full_url,
                                                'response_time': response_time,
                                                'source': server_url,
                                                'quality': 'GOOD' if response_time < 1.0 else 'NORMAL'
                                            })
                                            channel_count += 1
                        
                        if channel_count > 0:
                            logging.info(f"✅ Found {channel_count} channels from {server_url} using {json_path}")
                            break  # 找到有效路径就停止尝试
                        else:
                            logging.warning(f"❌ No valid channels found from {server_url} using {json_path}")
                            
                except requests.RequestException as e:
                    logging.debug(f"Request failed for {json_path}: {e}")
                    continue
                except Exception as e:
                    logging.debug(f"Error processing {json_path}: {e}")
                    continue
                    
            if not results:
                logging.warning(f"❌ No channels found from {server_url} after trying all paths")
                    
        except Exception as e:
            logging.error(f"❌ Error processing server {server_url}: {str(e)}")
        
        return results

    def process_all_servers(self):
        """处理所有服务器"""
        logging.info(f"\n{'='*60}")
        logging.info(f"🚀 Starting IPTV collection from {len(MAIN_SERVERS)} servers")
        logging.info(f"{'='*60}")
        
        try:
            all_results = []
            
            # 使用线程池并行处理所有服务器
            with ThreadPoolExecutor(max_workers=CONFIG['max_workers']) as executor:
                future_to_server = {
                    executor.submit(self.process_single_server, server): server 
                    for server in MAIN_SERVERS
                }
                
                completed = 0
                total = len(future_to_server)
                
                for future in as_completed(future_to_server):
                    completed += 1
                    server_url = future_to_server[future]
                    try:
                        results = future.result()
                        if results:
                            all_results.extend(results)
                            logging.info(f"✅ [{completed}/{total}] {server_url}: {len(results)} channels")
                        else:
                            logging.info(f"❌ [{completed}/{total}] {server_url}: No channels found")
                    except Exception as e:
                        logging.error(f"❌ [{completed}/{total}] {server_url}: Failed - {e}")
            
            # 按响应时间排序
            all_results.sort(key=lambda x: x['response_time'])
            
            logging.info(f"📊 Total: {len(all_results)} channels from {len(MAIN_SERVERS)} servers")
            return all_results
            
        except Exception as e:
            logging.error(f"❌ Error processing servers: {str(e)}")
            return []

    def save_results(self, results, filename, format='txt'):
        """保存结果到文件"""
        if not results:
            logging.warning(f"⚠️ No results to save for {filename}")
            return False
        
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else '.', exist_ok=True)
            
            if format == 'txt':
                with open(filename, "w", encoding="utf-8") as file:
                    file.write("# IPTV Channel List\n")
                    file.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    file.write(f"# Total Channels: {len(results)}\n")
                    file.write("# Format: ChannelName,URL\n")
                    file.write("# \n")
                    for result in results:
                        file.write(f"{result['name']},{result['url']}\n")
            
            elif format == 'm3u':
                with open(filename, "w", encoding="utf-8") as file:
                    file.write("#EXTM3U\n")
                    file.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    file.write(f"# Total Channels: {len(results)}\n")
                    file.write("# \n")
                    for result in results:
                        file.write(f"#EXTINF:-1 tvg-name=\"{result['name']}\",{result['name']}\n")
                        file.write(f"{result['url']}\n")
            
            logging.info(f"💾 Saved {len(results)} results to {filename}")
            return True
            
        except Exception as e:
            logging.error(f"❌ Error saving results to {filename}: {e}")
            return False

def remove_duplicate_channels(results):
    """去除重复频道（基于名称和URL）"""
    unique_channels = {}
    
    for result in results:
        key = (result['name'].lower(), result['url'])
        # 保留响应时间更短的版本
        if key not in unique_channels or result['response_time'] < unique_channels[key]['response_time']:
            unique_channels[key] = result
    
    return list(unique_channels.values())

def generate_stats(results):
    """生成统计信息"""
    if not results:
        return
    
    stats = {
        'cctv_count': 0,
        'local_count': 0,
        'other_count': 0,
        'sources': set(),
        'quality_good': 0,
        'quality_normal': 0
    }
    
    for result in results:
        stats['sources'].add(result['source'])
        if result['quality'] == 'GOOD':
            stats['quality_good'] += 1
        else:
            stats['quality_normal'] += 1
            
        if 'CCTV' in result['name']:
            stats['cctv_count'] += 1
        elif any(province in result['name'] for province in ['北京', '上海', '广东', '湖南', '浙江', '江苏']):
            stats['local_count'] += 1
        else:
            stats['other_count'] += 1
    
    logging.info(f"📊 Channel Statistics:")
    logging.info(f"   📺 CCTV Channels: {stats['cctv_count']}")
    logging.info(f"   🏠 Local Channels: {stats['local_count']}")
    logging.info(f"   🔄 Other Channels: {stats['other_count']}")
    logging.info(f"   ✅ Good Quality: {stats['quality_good']}")
    logging.info(f"   ⚠️  Normal Quality: {stats['quality_normal']}")
    logging.info(f"   🌐 Unique Sources: {len(stats['sources'])}")

def main():
    """主函数"""
    collector = IPTVCollector()
    start_time = time.time()
    
    logging.info("🚀 Starting IPTV collection process...")
    logging.info(f"📡 Total servers to process: {len(MAIN_SERVERS)}")
    
    # 处理所有服务器
    all_results = collector.process_all_servers()
    
    # 合并所有结果并去重
    if all_results:
        logging.info(f"\n🔄 Merging and deduplicating {len(all_results)} channels...")
        final_results = remove_duplicate_channels(all_results)
        final_results.sort(key=lambda x: (x['name'], x['response_time']))
        
        # 保存最终文件
        collector.save_results(final_results, "iptv.txt", 'txt')
        collector.save_results(final_results, "iptv.m3u", 'm3u')
        
        # 生成统计信息
        generate_stats(final_results)
        
        logging.info(f"✅ Merged {len(all_results)} channels into {len(final_results)} unique channels")
    else:
        logging.error("❌ No valid channels collected!")
        # 创建空的IPTV文件
        with open("iptv.txt", "w", encoding="utf-8") as f:
            f.write("# No channels collected\n")
        with open("iptv.m3u", "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n# No channels collected\n")
    
    # 输出总结
    end_time = time.time()
    processing_time = end_time - start_time
    
    logging.info(f"\n{'='*60}")
    logging.info("📊 COLLECTION SUMMARY")
    logging.info(f"{'='*60}")
    logging.info(f"⏱️  Processing time: {processing_time:.2f} seconds")
    logging.info(f"📺 Total channels collected: {len(all_results)}")
    logging.info(f"🎯 Unique channels: {len(final_results) if all_results else 0}")
    logging.info(f"📡 Servers processed: {len(MAIN_SERVERS)}")
    if all_results:
        logging.info(f"📈 Success rate: {len([r for r in all_results]) / len(MAIN_SERVERS) * 100:.1f}%")
    logging.info(f"💾 Output files: iptv.txt, iptv.m3u")
    logging.info(f"{'='*60}")

if __name__ == "__main__":
    main()
