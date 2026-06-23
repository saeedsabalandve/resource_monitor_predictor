# src/collector/collectors.py
# System resource metric collectors
# Uses psutil for cross-platform resource monitoring
# Collects detailed metrics for CPU, Memory, Disk, Network, and Processes

import psutil
import GPUtil
from typing import Dict, Any, List
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from loguru import logger


@dataclass
class MetricPoint:
    """Standardized metric data point structure"""
    timestamp: str
    resource_type: str
    metric_name: str
    value: float
    unit: str
    tags: Dict[str, str]


class BaseCollector:
    """Base class for resource collectors"""
    
    def __init__(self, resource_type: str):
        self.resource_type = resource_type
    
    def _create_metric(self, name: str, value: float, unit: str, **tags) -> MetricPoint:
        """Create standardized metric point"""
        return MetricPoint(
            timestamp=datetime.now(timezone.utc).isoformat(),
            resource_type=self.resource_type,
            metric_name=name,
            value=round(value, 2),
            unit=unit,
            tags=tags
        )


class CPUMetrics(BaseCollector):
    """
    CPU resource metrics collector
    Collects per-core and aggregate CPU statistics
    """
    
    def __init__(self):
        super().__init__("cpu")
    
    def collect(self) -> List[MetricPoint]:
        """Collect comprehensive CPU metrics"""
        metrics = []
        
        try:
            # Overall CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            metrics.append(
                self._create_metric("usage_percent", cpu_percent, "percent")
            )
            
            # Per-core CPU usage
            per_cpu = psutil.cpu_percent(interval=1, percpu=True)
            for i, percent in enumerate(per_cpu):
                metrics.append(
                    self._create_metric(
                        f"core_{i}_usage", 
                        percent, 
                        "percent",
                        core=str(i)
                    )
                )
            
            # CPU frequency
            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                metrics.append(
                    self._create_metric("frequency_current", cpu_freq.current, "MHz")
                )
            
            # CPU times
            cpu_times = psutil.cpu_times()
            metrics.append(
                self._create_metric("time_user", cpu_times.user, "seconds")
            )
            metrics.append(
                self._create_metric("time_system", cpu_times.system, "seconds")
            )
            metrics.append(
                self._create_metric("time_idle", cpu_times.idle, "seconds")
            )
            
            # Load average
            load_avg = psutil.getloadavg()
            metrics.append(
                self._create_metric("load_1min", load_avg[0], "load")
            )
            metrics.append(
                self._create_metric("load_5min", load_avg[1], "load")
            )
            metrics.append(
                self._create_metric("load_15min", load_avg[2], "load")
            )
            
            logger.debug(f"Collected {len(metrics)} CPU metrics")
            
        except Exception as e:
            logger.error(f"Error collecting CPU metrics: {e}")
        
        return metrics


class MemoryMetrics(BaseCollector):
    """
    Memory resource metrics collector
    Collects RAM and swap memory statistics
    """
    
    def __init__(self):
        super().__init__("memory")
    
    def collect(self) -> List[MetricPoint]:
        """Collect comprehensive memory metrics"""
        metrics = []
        
        try:
            # Virtual memory
            virtual_mem = psutil.virtual_memory()
            metrics.append(
                self._create_metric("total", virtual_mem.total, "bytes")
            )
            metrics.append(
                self._create_metric("available", virtual_mem.available, "bytes")
            )
            metrics.append(
                self._create_metric("used", virtual_mem.used, "bytes")
            )
            metrics.append(
                self._create_metric("used_percent", virtual_mem.percent, "percent")
            )
            metrics.append(
                self._create_metric("free", virtual_mem.free, "bytes")
            )
            
            # Swap memory
            swap_mem = psutil.swap_memory()
            metrics.append(
                self._create_metric("swap_total", swap_mem.total, "bytes")
            )
            metrics.append(
                self._create_metric("swap_used", swap_mem.used, "bytes")
            )
            metrics.append(
                self._create_metric("swap_percent", swap_mem.percent, "percent")
            )
            
            logger.debug(f"Collected {len(metrics)} Memory metrics")
            
        except Exception as e:
            logger.error(f"Error collecting Memory metrics: {e}")
        
        return metrics


class DiskMetrics(BaseCollector):
    """
    Disk I/O and usage metrics collector
    Collects per-partition disk statistics
    """
    
    def __init__(self):
        super().__init__("disk")
    
    def collect(self) -> List[MetricPoint]:
        """Collect comprehensive disk metrics"""
        metrics = []
        
        try:
            # Disk partitions
            partitions = psutil.disk_partitions()
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    metrics.append(
                        self._create_metric(
                            f"{partition.device}_total",
                            usage.total,
                            "bytes",
                            device=partition.device,
                            mountpoint=partition.mountpoint
                        )
                    )
                    metrics.append(
                        self._create_metric(
                            f"{partition.device}_used",
                            usage.used,
                            "bytes",
                            device=partition.device,
                            mountpoint=partition.mountpoint
                        )
                    )
                    metrics.append(
                        self._create_metric(
                            f"{partition.device}_used_percent",
                            usage.percent,
                            "percent",
                            device=partition.device,
                            mountpoint=partition.mountpoint
                        )
                    )
                except PermissionError:
                    logger.warning(f"Permission denied for partition: {partition.mountpoint}")
            
            # Disk I/O
            io_counters = psutil.disk_io_counters()
            if io_counters:
                metrics.append(
                    self._create_metric("read_bytes", io_counters.read_bytes, "bytes")
                )
                metrics.append(
                    self._create_metric("write_bytes", io_counters.write_bytes, "bytes")
                )
                metrics.append(
                    self._create_metric("read_count", io_counters.read_count, "count")
                )
                metrics.append(
                    self._create_metric("write_count", io_counters.write_count, "count")
                )
            
            logger.debug(f"Collected {len(metrics)} Disk metrics")
            
        except Exception as e:
            logger.error(f"Error collecting Disk metrics: {e}")
        
        return metrics


class NetworkMetrics(BaseCollector):
    """
    Network I/O metrics collector
    Collects per-interface network statistics
    """
    
    def __init__(self):
        super().__init__("network")
    
    def collect(self) -> List[MetricPoint]:
        """Collect comprehensive network metrics"""
        metrics = []
        
        try:
            # Per-interface statistics
            net_io = psutil.net_io_counters(pernic=True)
            for interface, counters in net_io.items():
                metrics.append(
                    self._create_metric(
                        f"{interface}_bytes_sent",
                        counters.bytes_sent,
                        "bytes",
                        interface=interface
                    )
                )
                metrics.append(
                    self._create_metric(
                        f"{interface}_bytes_recv",
                        counters.bytes_recv,
                        "bytes",
                        interface=interface
                    )
                )
                metrics.append(
                    self._create_metric(
                        f"{interface}_packets_sent",
                        counters.packets_sent,
                        "packets",
                        interface=interface
                    )
                )
                metrics.append(
                    self._create_metric(
                        f"{interface}_packets_recv",
                        counters.packets_recv,
                        "packets",
                        interface=interface
                    )
                )
                
                # Error statistics
                if hasattr(counters, 'errin'):
                    metrics.append(
                        self._create_metric(
                            f"{interface}_errors_in",
                            counters.errin,
                            "errors",
                            interface=interface
                        )
                    )
                if hasattr(counters, 'errout'):
                    metrics.append(
                        self._create_metric(
                            f"{interface}_errors_out",
                            counters.errout,
                            "errors",
                            interface=interface
                        )
                    )
            
            # Network connections
            connections = len(psutil.net_connections())
            metrics.append(
                self._create_metric("active_connections", connections, "connections")
            )
            
            logger.debug(f"Collected {len(metrics)} Network metrics")
            
        except Exception as e:
            logger.error(f"Error collecting Network metrics: {e}")
        
        return metrics


class ProcessMetrics(BaseCollector):
    """
    Process-level metrics collector
    Collects process count and top resource consumers
    """
    
    def __init__(self):
        super().__init__("process")
    
    def collect(self) -> List[MetricPoint]:
        """Collect process-related metrics"""
        metrics = []
        
        try:
            # Total process count
            process_count = len(psutil.pids())
            metrics.append(
                self._create_metric("total_count", process_count, "processes")
            )
            
            # Top CPU-consuming processes
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Sort by CPU usage and get top 5
            top_cpu = sorted(
                [p for p in processes if p['cpu_percent'] is not None],
                key=lambda x: x['cpu_percent'],
                reverse=True
            )[:5]
            
            for proc in top_cpu:
                metrics.append(
                    self._create_metric(
                        f"top_cpu_{proc['pid']}",
                        proc['cpu_percent'],
                        "percent",
                        pid=str(proc['pid']),
                        name=proc['name']
                    )
                )
            
            logger.debug(f"Collected {len(metrics)} Process metrics")
            
        except Exception as e:
            logger.error(f"Error collecting Process metrics: {e}")
        
        return metrics
