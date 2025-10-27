import sys
import time
import socket
import requests
import json
import re
import os
import threading
import ipaddress
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('iptv_system.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class IPTVScanner:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Connection': 'keep-alive'
        })
        self.timeout = 3
        self.found_servers = []
        self.lock = threading.Lock()
        
        # 常见的IPTV端口
        self.common_ports = [80, 8080, 8000, 8001, 8002, 8081, 8082, 8090, 8888, 9000]
        
        # 常见的IPTV JSON路径
        self.json_paths = [
            "/iptv/live/1000.json?key=txiptv",
            "/iptv/live/1000.json",
            "/live/1000.json",
            "/tv/1000.json",
            "/iptv/live.json",
            "/api/live",
            "/live.json"
        ]

    def generate_ip_ranges(self):
        """生成常见的国内IP段"""
        ip_ranges = []
        
        # 电信IP段
        telecom_ranges = [
            "58.16.0.0/16", "58.17.0.0/16", "58.18.0.0/16", "58.19.0.0/16",
            "60.0.0.0/11", "60.160.0.0/11", "60.208.0.0/12",
            "113.0.0.0/13", "113.8.0.0/15", "113.16.0.0/12",
            "114.80.0.0/12", "114.96.0.0/13", "114.104.0.0/14",
            "115.48.0.0/12", "115.152.0.0/13", "115.160.0.0/12",
            "116.1.0.0/16", "116.2.0.0/15", "116.4.0.0/14",
            "117.8.0.0/13", "117.16.0.0/12", "117.32.0.0/11",
            "118.74.0.0/15", "118.76.0.0/16", "118.80.0.0/13",
            "119.0.0.0/13", "119.8.0.0/15", "119.10.0.0/16"
        ]
        
        # 联通IP段
        unicom_ranges = [
            "60.8.0.0/13", "60.16.0.0/12", "60.24.0.0/13",
            "61.128.0.0/10", "61.160.0.0/12", "61.176.0.0/13",
            "111.0.0.0/10", "111.64.0.0/12", "111.80.0.0/13",
            "112.0.0.0/10", "112.64.0.0/14", "112.80.0.0/12",
            "113.200.0.0/15", "113.202.0.0/16", "113.204.0.0/14",
            "114.224.0.0/12", "114.240.0.0/12", "115.24.0.0/14"
        ]
        
        # 移动IP段
        mobile_ranges = [
            "111.0.0.0/10", "111.64.0.0/12", "111.80.0.0/13",
            "112.0.0.0/10", "112.64.0.0/14", "112.80.0.0/12",
            "113.200.0.0/15", "113.202.0.0/16", "113.204.0.0/14",
            "114.224.0.0/12", "114.240.0.0/12", "115.24.0.0/14"
        ]
        
        all_ranges = telecom_ranges + unicom_ranges + mobile_ranges
        
        # 随机选择一些IP段进行扫描
        selected_ranges = random.sample(all_ranges, min(10, len(all_ranges)))
        
        for ip_range in selected_ranges:
            network = ipaddress.ip_network(ip_range, strict=False)
            # 从每个网段中随机选择一些IP
            ip_count = min(20, network.num_addresses)
            for _ in range(ip_count):
                ip = str(network[random.randint(0, network.num_addresses - 1)])
                ip_ranges.append(ip)
                
        return ip_ranges

    def test_port(self, ip, port):
        """测试端口是否开放"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except:
            return False

    def test_iptv_server(self, ip, port):
        """测试是否为有效的IPTV服务器"""
        base_url = f"http://{ip}:{port}"
        
        for json_path in self.json_paths:
            try:
                url = urljoin(base_url, json_path)
                response = self.session.get(url, timeout=self.timeout)
                
                if response.status_code == 200:
                    # 检查返回内容是否为有效的JSON
                    try:
                        data = response.json()
                        # 检查JSON结构是否包含频道数据
                        if isinstance(data, dict) and 'data' in data:
                            if isinstance(data['data'], list) and len(data['data']) > 0:
                                return True, url, len(data['data'])
                        elif isinstance(data, list) and len(data) > 0:
                            return True, url, len(data)
                    except:
                        continue
            except:
                continue
                
        return False, None, 0

    def scan_single_ip(self, ip):
        """扫描单个IP的所有常见端口"""
        for port in self.common_ports:
            if self.test_port(ip, port):
                logging.info(f"✅ Port {port} open on {ip}")
                is_iptv, url, channel_count = self.test_iptv_server(ip, port)
                if is_iptv:
                    with self.lock:
                        self.found_servers.append({
                            'ip': ip,
                            'port': port,
                            'url': url,
                            'channel_count': channel_count,
                            'server_url': f"http://{ip}:{port}"
                        })
                    logging.info(f"🎯 Found IPTV server: {ip}:{port} with {channel_count} channels")
                    break  # 找到一个有效服务就停止扫描该IP的其他端口
                
        return []

    def quick_scan_common_servers(self):
        """快速扫描已知的常见服务器"""
        common_servers = [
            "60.214.107.42", "113.57.127.43", "58.222.24.11",
            "117.169.120.140", "112.30.144.207", "183.134.100.98",
            "60.214.107.43", "113.57.127.44", "58.222.24.12",
            "117.169.120.141", "112.30.144.208"
        ]
        
        logging.info("🔍 Quick scanning common IPTV servers...")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ip = {executor.submit(self.scan_single_ip, ip): ip for ip in common_servers}
            
            for future in as_completed(future_to_ip):
                ip = future_to_ip[future]
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"❌ Error scanning {ip}: {e}")
                    
        return len(self.found_servers)

    def deep_scan_network(self, max_ips=100):
        """深度扫描网络"""
        logging.info("🌐 Starting deep network scan...")
        ip_list = self.generate_ip_ranges()
        
        # 限制扫描的IP数量
        ip_list = ip_list[:max_ips]
        
        logging.info(f"📡 Scanning {len(ip_list)} IP addresses...")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ip = {executor.submit(self.scan_single_ip, ip): ip for ip in ip_list}
            
            for i, future in enumerate(as_completed(future_to_ip)):
                ip = future_to_ip[future]
                try:
                    future.result()
                    if (i + 1) % 20 == 0:
                        logging.info(f"📊 Progress: {i+1}/{len(ip_list)} - Found: {len(self.found_servers)} servers")
                except Exception as e:
                    logging.debug(f"Error scanning {ip}: {e}")
                    
        return len(self.found_servers)

    def save_found_servers(self, filename="discovered_servers.txt"):
        """保存发现的服务器"""
        if not self.found_servers:
            logging.warning("⚠️ No servers to save")
            return
            
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write("# Discovered IPTV Servers\n")
                f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Total Servers: {len(self.found_servers)}\n")
                f.write("# Format: ServerURL,IP,Port,ChannelCount\n")
                f.write("# \n")
                
                for server in self.found_servers:
                    f.write(f"{server['server_url']},{server['ip']},{server['port']},{server['channel_count']}\n")
                    
            logging.info(f"💾 Saved {len(self.found_servers)} servers to {filename}")
        except Exception as e:
            logging.error(f"❌ Error saving servers: {e}")

    def load_servers_for_collection(self):
        """为频道收集准备服务器列表"""
        return [server['server_url'] for server in self.found_servers]

class IPTVCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Connection': 'keep-alive'
        })

    def load_servers_from_file(self, filename="discovered_servers.txt"):
        """从文件加载服务器列表"""
        servers = []
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            parts = line.split(',')
                            if parts and parts[0].startswith('http'):
                                servers.append(parts[0])
                logging.info(f"📁 Loaded {len(servers)} servers from {filename}")
            except Exception as e:
                logging.warning(f"⚠️ Could not load servers from file: {e}")
        return servers

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
                    
                    response = self.session.get(json_url, timeout=8)
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

    def process_all_servers(self, servers):
        """处理所有服务器"""
        logging.info(f"\n{'='*60}")
        logging.info(f"🚀 Starting IPTV collection from {len(servers)} servers")
        logging.info(f"{'='*60}")
        
        try:
            all_results = []
            
            # 使用线程池并行处理所有服务器
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_server = {
                    executor.submit(self.process_single_server, server): server 
                    for server in servers
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
            
            logging.info(f"📊 Total: {len(all_results)} channels from {len(servers)} servers")
            return all_results
            
        except Exception as e:
            logging.error(f"❌ Error processing servers: {str(e)}")
            return []

    def categorize_channels(self, results):
        """将频道分类为央视和卫视"""
        cctv_channels = []
        satellite_channels = []
        other_channels = []
        
        # 央视频道关键词
        cctv_keywords = ['CCTV', '央视']
        # 卫视频道关键词 - 各省卫视
        satellite_keywords = [
            '北京', '上海', '天津', '重庆', '河北', '山西', '辽宁', '吉林', '黑龙江',
            '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南', '湖北', '湖南',
            '广东', '海南', '四川', '贵州', '云南', '陕西', '甘肃', '青海', '台湾',
            '内蒙古', '广西', '西藏', '宁夏', '新疆', '香港', '澳门',
            '卫视', '湖南卫视', '浙江卫视', '江苏卫视', '东方卫视', '北京卫视'
        ]
        
        for channel in results:
            name = channel['name']
            is_cctv = any(keyword in name for keyword in cctv_keywords)
            is_satellite = any(keyword in name for keyword in satellite_keywords)
            
            if is_cctv:
                cctv_channels.append(channel)
            elif is_satellite:
                satellite_channels.append(channel)
            else:
                other_channels.append(channel)
        
        return {
            'cctv': cctv_channels,
            'satellite': satellite_channels,
            'other': other_channels
        }

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
                    # 对频道进行分类
                    categorized = self.categorize_channels(results)
                    
                    # 写入央视频道
                    if categorized['cctv']:
                        file.write("央视频道,#genre#\n")
                        for channel in categorized['cctv']:
                            file.write(f"{channel['name']},{channel['url']}\n")
                        file.write("\n")
                    
                    # 写入卫视频道
                    if categorized['satellite']:
                        file.write("卫视频道,#genre#\n")
                        for channel in categorized['satellite']:
                            file.write(f"{channel['name']},{channel['url']}\n")
                        file.write("\n")
                    
                    # 写入其他频道
                    if categorized['other']:
                        file.write("其他频道,#genre#\n")
                        for channel in categorized['other']:
                            file.write(f"{channel['name']},{channel['url']}\n")
            
            elif format == 'm3u':
                with open(filename, "w", encoding="utf-8") as file:
                    file.write("#EXTM3U\n")
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
    
    # 创建收集器实例用于分类
    collector = IPTVCollector()
    categorized = collector.categorize_channels(results)
    
    stats = {
        'cctv_count': len(categorized['cctv']),
        'satellite_count': len(categorized['satellite']),
        'other_count': len(categorized['other']),
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
    
    logging.info(f"📊 Channel Statistics:")
    logging.info(f"   📺 CCTV Channels: {stats['cctv_count']}")
    logging.info(f"   🛰️ Satellite Channels: {stats['satellite_count']}")
    logging.info(f"   🔄 Other Channels: {stats['other_count']}")
    logging.info(f"   ✅ Good Quality: {stats['quality_good']}")
    logging.info(f"   ⚠️  Normal Quality: {stats['quality_normal']}")
    logging.info(f"   🌐 Unique Sources: {len(stats['sources'])}")

def run_scanner():
    """运行扫描器"""
    scanner = IPTVScanner()
    start_time = time.time()
    
    logging.info("🚀 Starting IPTV Server Scanner")
    logging.info("=" * 50)
    
    # 1. 快速扫描已知服务器
    logging.info("🔍 Phase 1: Quick scan of known servers...")
    quick_results = scanner.quick_scan_common_servers()
    
    # 2. 深度网络扫描（在GitHub Actions中减少扫描数量）
    logging.info("🌐 Phase 2: Light network scan...")
    deep_scan_count = scanner.deep_scan_network(max_ips=50)
    
    # 保存结果
    scanner.save_found_servers()
    
    # 统计信息
    end_time = time.time()
    processing_time = end_time - start_time
    
    logging.info("=" * 50)
    logging.info("📊 SCAN SUMMARY")
    logging.info("=" * 50)
    logging.info(f"⏱️  Processing time: {processing_time:.2f} seconds")
    logging.info(f"🎯 Total servers found: {len(scanner.found_servers)}")
    
    if scanner.found_servers:
        logging.info("\n📋 Discovered Servers:")
        for server in scanner.found_servers[:5]:
            logging.info(f"   📺 {server['ip']}:{server['port']} - {server['channel_count']} channels")
        
        if len(scanner.found_servers) > 5:
            logging.info(f"   ... and {len(scanner.found_servers) - 5} more servers")
    
    logging.info("=" * 50)
    
    return scanner.load_servers_for_collection()

def run_collector(servers=None):
    """运行收集器"""
    collector = IPTVCollector()
    start_time = time.time()
    
    # 如果没有提供服务器，尝试从文件加载
    if servers is None:
        servers = collector.load_servers_from_file()
    
    # 如果没有发现服务器，使用默认服务器
    if not servers:
        default_servers = [
            "http://60.214.107.42:8080",
            "http://113.57.127.43:8080", 
            "http://58.222.24.11:8080",
            "http://117.169.120.140:8080",
            "http://112.30.144.207:8080"
        ]
        servers = default_servers
        logging.info("📡 Using default servers for collection")
    
    logging.info("🚀 Starting IPTV collection process...")
    logging.info(f"📡 Total servers to process: {len(servers)}")
    
    # 处理所有服务器
    all_results = collector.process_all_servers(servers)
    
    # 合并所有结果并去重
    if all_results:
        logging.info(f"\n🔄 Merging and deduplicating {len(all_results)} channels...")
        final_results = remove_duplicate_channels(all_results)
        final_results.sort(key=lambda x: (x['name'], x['response_time']))
        
        # 分类统计
        categorized = collector.categorize_channels(final_results)
        logging.info(f"📺 Channel Categories:")
        logging.info(f"   📺 CCTV: {len(categorized['cctv'])} channels")
        logging.info(f"   🛰️ Satellite: {len(categorized['satellite'])} channels")
        logging.info(f"   🔄 Other: {len(categorized['other'])} channels")
        
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
            f.write("央视频道,#genre#\n")
            f.write("卫视频道,#genre#\n")
        with open("iptv.m3u", "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
    
    # 输出总结
    end_time = time.time()
    processing_time = end_time - start_time
    
    logging.info(f"\n{'='*60}")
    logging.info("📊 COLLECTION SUMMARY")
    logging.info(f"{'='*60}")
    logging.info(f"⏱️  Processing time: {processing_time:.2f} seconds")
    logging.info(f"📺 Total channels collected: {len(all_results)}")
    logging.info(f"🎯 Unique channels: {len(final_results) if all_results else 0}")
    logging.info(f"📡 Servers processed: {len(servers)}")
    logging.info(f"💾 Output files: iptv.txt, iptv.m3u")
    logging.info(f"{'='*60}")

def main():
    """主函数"""
    # 检查是否在非交互环境中运行（如GitHub Actions）
    if not sys.stdin.isatty():
        logging.info("🤖 Running in non-interactive mode (GitHub Actions)")
        logging.info("🚀 Starting full IPTV collection process...")
        
        # 运行扫描器
        servers = run_scanner()
        
        # 运行收集器
        if servers:
            run_collector(servers)
        else:
            logging.warning("⚠️ No servers found during scan, using default servers")
            run_collector()
        return
    
    # 原有的交互式菜单代码（用于本地运行）
    print("\n" + "="*60)
    print("🎯 IPTV System - Complete Solution")
    print("="*60)
    print("1. 🔍 Scan for IPTV servers")
    print("2. 📺 Collect channels from existing servers")
    print("3. 🚀 Scan and collect (full process)")
    print("4. 📁 Collect from discovered servers")
    print("="*60)
    
    try:
        choice = input("Select option (1-4): ").strip()
        
        if choice == "1":
            run_scanner()
        elif choice == "2":
            run_collector()
        elif choice == "3":
            servers = run_scanner()
            if servers:
                run_collector(servers)
            else:
                run_collector()
        elif choice == "4":
            run_collector()
        else:
            logging.error("❌ Invalid choice!")
    except EOFError:
        # 处理非交互环境中的EOF错误
        logging.info("🚀 Auto-selecting full process in non-interactive environment")
        servers = run_scanner()
        if servers:
            run_collector(servers)
        else:
            run_collector()
    except KeyboardInterrupt:
        logging.info("👋 Operation cancelled by user")

if __name__ == "__main__":
    main()
