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

class OptimizedIPTVScanner:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Connection': 'keep-alive'
        })
        self.timeout = 1
        self.found_servers = []
        self.lock = threading.Lock()
        self.scan_stats = {
            'ips_scanned': 0,
            'ports_tested': 0,
            'servers_found': 0,
            'start_time': time.time()
        }
        
        # 优化端口列表 - 只扫描最有可能的端口
        self.optimized_ports = [
            80, 8080, 8000, 8001, 8002, 8081, 8082, 8090, 8888, 9000,
            81, 82, 83, 84, 85, 86, 88, 8008, 8010, 8088,
            7000, 7080, 8009, 8011, 8089, 8091, 8099, 8880, 9001
        ]
        
        # 最有效的JSON路径
        self.effective_paths = [
            "/iptv/live/1000.json?key=txiptv",
            "/iptv/live/1000.json",
            "/live/1000.json",
            "/tv/1000.json"
        ]

    def get_high_value_prefixes(self):
        """获取高价值的IP前缀（基于已知有效服务器）"""
        high_value_prefixes = [
            # 已知有效的IPTV服务器段
            "60.214", "113.57", "58.222", "117.169", "112.30",
            "183.134", "124.112", "123.132", "122.192",
            
            # 高概率的电信段
            "58.16", "58.17", "58.18", "58.19", "58.20",
            "60.0", "60.1", "60.2", "60.3", "60.4",
            "61.128", "61.129", "61.130", "61.131",
            "113.0", "113.1", "113.2", "113.3", "113.4",
            "114.80", "114.81", "114.82", "114.83",
            "115.48", "115.49", "115.50", "115.51",
            
            # 高概率的联通段
            "60.8", "60.9", "60.10", "60.11", "60.12",
            "61.160", "61.161", "61.162", "61.163",
            "111.0", "111.1", "111.2", "111.3", "111.4",
            "112.0", "112.1", "112.2", "112.3", "112.4",
            
            # 高概率的移动段
            "120.192", "120.193", "120.194", "120.195",
            "121.0", "121.1", "121.2", "121.3", "121.4"
        ]
        
        return list(set(high_value_prefixes))

    def generate_target_ips(self, ip_prefix, target_count=500):
        """生成目标IP（智能选择，不是随机）"""
        ip_list = []
        base_parts = ip_prefix.split('.')
        
        if len(base_parts) != 2:
            return ip_list
        
        # 策略1: 扫描已知的有效IP范围
        known_ranges = [
            (1, 50),    # 常用服务器范围
            (100, 150), # 次要服务器范围  
            (200, 220), # 可能服务器范围
        ]
        
        for range_start, range_end in known_ranges:
            for third in range(range_start, range_end + 1):
                for fourth in range(1, 255):
                    ip = f"{base_parts[0]}.{base_parts[1]}.{third}.{fourth}"
                    ip_list.append(ip)
                    if len(ip_list) >= target_count:
                        return ip_list
        
        # 如果还不够，补充随机IP
        while len(ip_list) < target_count:
            third = random.randint(1, 254)
            fourth = random.randint(1, 254)
            ip = f"{base_parts[0]}.{base_parts[1]}.{third}.{fourth}"
            if ip not in ip_list:
                ip_list.append(ip)
        
        return ip_list

    def ultra_fast_port_check(self, ip, port):
        """超快速端口检查"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)  # 非常短的超时
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except:
            return False

    def quick_iptv_validation(self, ip, port):
        """快速IPTV验证"""
        test_urls = [
            f"http://{ip}:{port}/iptv/live/1000.json?key=txiptv",
            f"http://{ip}:{port}/iptv/live/1000.json",
            f"http://{ip}:{port}/live/1000.json",
            f"http://{ip}:{port}/tv/1000.json"
        ]
        
        for url in test_urls:
            try:
                response = self.session.get(url, timeout=1)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        # 快速验证数据结构
                        if isinstance(data, dict) and 'data' in data:
                            if isinstance(data['data'], list) and len(data['data']) > 10:  # 至少有10个频道
                                return True, url, len(data['data'])
                        elif isinstance(data, list) and len(data) > 10:
                            return True, url, len(data)
                    except:
                        continue
            except:
                continue
                
        return False, None, 0

    def scan_ip_port_combination(self, ip_port_tuple):
        """扫描单个IP端口组合"""
        ip, port = ip_port_tuple
        
        if self.ultra_fast_port_check(ip, port):
            is_iptv, url, channel_count = self.quick_iptv_validation(ip, port)
            if is_iptv:
                with self.lock:
                    self.found_servers.append({
                        'ip': ip,
                        'port': port,
                        'url': url,
                        'channel_count': channel_count,
                        'server_url': f"http://{ip}:{port}",
                        'scan_time': time.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    self.scan_stats['servers_found'] += 1
                logging.info(f"🎯 FOUND: {ip}:{port} - {channel_count} channels")
                return True
        
        with self.lock:
            self.scan_stats['ports_tested'] += 1
        
        return False

    def scan_prefix_optimized(self, ip_prefix):
        """优化扫描单个IP前缀"""
        logging.info(f"🔍 Scanning: {ip_prefix}.*.*")
        
        # 生成目标IP
        target_ips = self.generate_target_ips(ip_prefix, 300)  # 扫描300个IP
        logging.info(f"📊 Targeting {len(target_ips)} IPs with {len(self.optimized_ports)} ports")
        
        # 创建所有IP端口组合
        ip_port_combinations = []
        for ip in target_ips:
            for port in self.optimized_ports:
                ip_port_combinations.append((ip, port))
        
        total_combinations = len(ip_port_combinations)
        found_count = 0
        
        # 分批扫描
        batch_size = 1000
        for i in range(0, total_combinations, batch_size):
            batch = ip_port_combinations[i:i + batch_size]
            
            with ThreadPoolExecutor(max_workers=25) as executor:  # 增加工作线程
                future_to_combo = {executor.submit(self.scan_ip_port_combination, combo): combo for combo in batch}
                
                batch_found = 0
                for future in as_completed(future_to_combo):
                    try:
                        if future.result():
                            batch_found += 1
                    except:
                        pass
            
            found_count += batch_found
            
            # 进度显示
            progress = min(i + batch_size, total_combinations)
            elapsed = time.time() - self.scan_stats['start_time']
            
            with self.lock:
                ips_done = len(set([combo[0] for combo in ip_port_combinations[:progress]]))
                self.scan_stats['ips_scanned'] = ips_done
            
            logging.info(f"📊 {ip_prefix}: {progress}/{total_combinations} - "
                        f"IPs: {ips_done}/{len(target_ips)} - "
                        f"Found: {found_count} - "
                        f"Total: {self.scan_stats['servers_found']} servers")
            
            # 如果这个前缀找到了服务器，继续扫描
            if found_count > 0:
                logging.info(f"✅ Good results from {ip_prefix}, continuing...")
            else:
                # 如果扫描了一半还没找到，考虑跳过
                if progress >= total_combinations // 2 and found_count == 0:
                    logging.info(f"⏩ No servers in {ip_prefix}, moving to next...")
                    break
        
        return found_count

    def run_fast_scan(self, max_prefixes=5):
        """运行快速扫描"""
        prefixes = self.get_high_value_prefixes()[:max_prefixes]
        
        logging.info("🚀 STARTING OPTIMIZED IPTV SCAN")
        logging.info("=" * 60)
        logging.info(f"📡 Scanning {len(prefixes)} high-value prefixes")
        logging.info(f"🎯 Ports: {len(self.optimized_ports)} optimized ports")
        logging.info(f"⚡ Timeout: 0.5s port check, 1s HTTP request")
        logging.info("=" * 60)
        
        total_found = 0
        
        for i, prefix in enumerate(prefixes):
            start_prefix_time = time.time()
            
            prefix_found = self.scan_prefix_optimized(prefix)
            total_found += prefix_found
            
            prefix_time = time.time() - start_prefix_time
            logging.info(f"✅ {prefix}: {prefix_found} servers in {prefix_time:.1f}s")
            
            # 实时保存
            self.save_progress()
            
            # 检查总时间，避免超时
            total_time = time.time() - self.scan_stats['start_time']
            if total_time > 480:  # 8分钟
                logging.info("⏰ Time limit reached, stopping scan")
                break
        
        return total_found

    def save_progress(self, filename="optimized_servers.txt"):
        """保存进度"""
        if not self.found_servers:
            return
        
        try:
            sorted_servers = sorted(self.found_servers, key=lambda x: x['channel_count'], reverse=True)
            
            with open(filename, "w", encoding="utf-8") as f:
                f.write("# OPTIMIZED IPTV SERVER LIST\n")
                f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Total Servers: {len(self.found_servers)}\n")
                f.write(f"# Scan Time: {time.time() - self.scan_stats['start_time']:.1f}s\n")
                f.write("# Format: ServerURL,ChannelCount\n")
                f.write("# \n")
                
                for server in sorted_servers:
                    f.write(f"{server['server_url']},{server['channel_count']}\n")
            
            # 同时保存用于收集的列表
            with open("discovered_servers.txt", "w", encoding="utf-8") as f:
                for server in sorted_servers:
                    f.write(f"{server['server_url']}\n")
                    
            logging.info(f"💾 Progress saved: {len(self.found_servers)} servers")
            
        except Exception as e:
            logging.error(f"❌ Error saving: {e}")

    def show_stats(self):
        """显示统计"""
        elapsed = time.time() - self.scan_stats['start_time']
        
        logging.info("\n" + "=" * 60)
        logging.info("📊 SCAN COMPLETED")
        logging.info("=" * 60)
        logging.info(f"⏱️  Time: {elapsed:.1f}s")
        logging.info(f"🔍 IPs: {self.scan_stats['ips_scanned']}")
        logging.info(f"🎯 Ports: {self.scan_stats['ports_tested']}")
        logging.info(f"🚀 Servers: {self.scan_stats['servers_found']}")
        
        if self.found_servers:
            best_servers = sorted(self.found_servers, key=lambda x: x['channel_count'], reverse=True)[:10]
            logging.info("\n🏆 Top Servers:")
            for i, server in enumerate(best_servers, 1):
                logging.info(f"   {i}. {server['ip']}:{server['port']} - {server['channel_count']} channels")
        
        logging.info("=" * 60)

def run_optimized_scan():
    """运行优化扫描"""
    scanner = OptimizedIPTVScanner()
    
    try:
        # 在8分钟内完成扫描
        total_found = scanner.run_fast_scan(max_prefixes=3)
        scanner.show_stats()
        scanner.save_progress()
        return len(scanner.found_servers)
        
    except Exception as e:
        logging.error(f"❌ Scan error: {e}")
        scanner.show_stats()
        scanner.save_progress()
        return len(scanner.found_servers)

# 主函数
def main():
    """主函数"""
    if not sys.stdin.isatty():
        logging.info("🤖 Starting OPTIMIZED IPTV Scanner")
        server_count = run_optimized_scan()
        
        if server_count > 0:
            logging.info(f"✅ Scan success: {server_count} servers found")
        else:
            logging.info("❌ No servers found, using defaults")
            # 创建默认服务器文件
            with open("discovered_servers.txt", "w", encoding="utf-8") as f:
                f.write("http://60.214.107.42:8080\n")
                f.write("http://113.57.127.43:8080\n")
                f.write("http://58.222.24.11:8080\n")
    else:
        print("\n🎯 OPTIMIZED IPTV SCANNER")
        print("⚡ Fast scanning with optimized strategy")
        server_count = run_optimized_scan()
        print(f"\n✅ Found {server_count} servers")

if __name__ == "__main__":
    main()
