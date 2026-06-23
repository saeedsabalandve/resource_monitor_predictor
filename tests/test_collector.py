# tests/test_collector.py
# Unit tests for resource collectors
# Tests metric collection accuracy and performance

import pytest
from unittest.mock import Mock, patch
from datetime import datetime
import psutil

from src.collector.collectors import (
    CPUMetrics,
    MemoryMetrics,
    DiskMetrics,
    NetworkMetrics,
    ProcessMetrics,
    MetricPoint
)


class TestCPUMetrics:
    """Test CPU metrics collector"""
    
    def test_collector_initialization(self):
        """Test CPU collector initialization"""
        collector = CPUMetrics()
        assert collector.resource_type == "cpu"
    
    @patch('psutil.cpu_percent')
    @patch('psutil.cpu_freq')
    @patch('psutil.cpu_times')
    @patch('psutil.getloadavg')
    def test_collect_cpu_metrics(self, mock_loadavg, mock_times, mock_freq, mock_percent):
        """Test CPU metric collection"""
        # Mock psutil responses
        mock_percent.side_effect = [45.5, [40.0, 45.0, 50.0, 47.0]]  # overall, per-core
        
        mock_freq_obj = Mock()
        mock_freq_obj.current = 2400.0
        mock_freq.return_value = mock_freq_obj
        
        mock_times_obj = Mock()
        mock_times_obj.user = 1000.0
        mock_times_obj.system = 500.0
        mock_times_obj.idle = 5000.0
        mock_times.return_value = mock_times_obj
        
        mock_loadavg.return_value = (1.5, 2.0, 2.5)
        
        collector = CPUMetrics()
        metrics = collector.collect()
        
        # Verify metrics collection
        assert len(metrics) > 0
        assert any(m.metric_name == "usage_percent" for m in metrics)
        assert any(m.metric_name == "frequency_current" for m in metrics)
        
        # Check specific metric values
        usage_metric = next(m for m in metrics if m.metric_name == "usage_percent")
        assert usage_metric.value == 45.5
        assert usage_metric.unit == "percent"
    
    def test_metric_point_structure(self):
        """Test MetricPoint dataclass structure"""
        metric = MetricPoint(
            timestamp="2024-01-01T00:00:00",
            resource_type="cpu",
            metric_name="usage_percent",
            value=50.5,
            unit="percent",
            tags={"core": "0"}
        )
        
        assert metric.resource_type == "cpu"
        assert metric.value == 50.5
        assert metric.tags["core"] == "0"


class TestMemoryMetrics:
    """Test Memory metrics collector"""
    
    @patch('psutil.virtual_memory')
    @patch('psutil.swap_memory')
    def test_collect_memory_metrics(self, mock_swap, mock_virtual):
        """Test memory metric collection"""
        # Mock virtual memory
        mock_virtual_obj = Mock()
        mock_virtual_obj.total = 16000000000
        mock_virtual_obj.available = 8000000000
        mock_virtual_obj.used = 8000000000
        mock_virtual_obj.percent = 50.0
        mock_virtual_obj.free = 2000000000
        mock_virtual.return_value = mock_virtual_obj
        
        # Mock swap memory
        mock_swap_obj = Mock()
        mock_swap_obj.total = 4000000000
        mock_swap_obj.used = 1000000000
        mock_swap_obj.percent = 25.0
        mock_swap.return_value = mock_swap_obj
        
        collector = MemoryMetrics()
        metrics = collector.collect()
        
        assert len(metrics) > 0
        assert any(m.metric_name == "used_percent" for m in metrics)
        
        # Check memory usage percentage
        usage_metric = next(m for m in metrics if m.metric_name == "used_percent")
        assert usage_metric.value == 50.0


class TestDiskMetrics:
    """Test Disk metrics collector"""
    
    @patch('psutil.disk_partitions')
    @patch('psutil.disk_usage')
    @patch('psutil.disk_io_counters')
    def test_collect_disk_metrics(self, mock_io, mock_usage, mock_partitions):
        """Test disk metric collection"""
        # Mock partitions
        mock_partition = Mock()
        mock_partition.device = '/dev/sda1'
        mock_partition.mountpoint = '/'
        mock_partitions.return_value = [mock_partition]
        
        # Mock disk usage
        mock_usage_obj = Mock()
        mock_usage_obj.total = 100000000000
        mock_usage_obj.used = 60000000000
        mock_usage_obj.percent = 60.0
        mock_usage.return_value = mock_usage_obj
        
        # Mock I/O counters
        mock_io_obj = Mock()
        mock_io_obj.read_bytes = 1000000
        mock_io_obj.write_bytes = 500000
        mock_io_obj.read_count = 100
        mock_io_obj.write_count = 50
        mock_io.return_value = mock_io_obj
        
        collector = DiskMetrics()
        metrics = collector.collect()
        
        assert len(metrics) > 0
        
        # Check disk usage percentage
        usage_metrics = [m for m in metrics if 'used_percent' in m.metric_name]
        assert len(usage_metrics) > 0
        assert usage_metrics[0].value == 60.0


@pytest.mark.asyncio
class TestCollectionScheduler:
    """Test collection scheduler"""
    
    @pytest.fixture
    async def scheduler(self):
        """Create test scheduler"""
        from src.collector.scheduler import CollectionScheduler
        from config.settings import Settings
        
        settings = Settings()
        mock_influx = Mock()
        
        scheduler = CollectionScheduler(settings, mock_influx)
        return scheduler
    
    async def test_scheduler_initialization(self, scheduler):
        """Test scheduler initialization"""
        assert scheduler is not None
        assert 'cpu' in scheduler.collectors
        assert 'memory' in scheduler.collectors
        assert scheduler.intervals['cpu'] > 0
    
    async def test_manual_collection(self, scheduler):
        """Test manual collection trigger"""
        # Mock the collect_and_store method
        scheduler.collect_and_store = Mock()
        
        await scheduler.trigger_manual_collection('cpu')
        scheduler.collect_and_store.assert_called_once_with('cpu')
