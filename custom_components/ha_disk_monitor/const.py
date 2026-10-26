"""Constants for the Disk Monitor integration."""

DOMAIN = "ha_disk_monitor"
DEFAULT_NAME = "Disk Monitor"
MANUFACTURER = "disk-agent"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"
CONF_API_KEY = "api_key"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_PERSISTENT = "persistent_notifications"
CONF_NOTIFY_DEVICES = "notify_devices"

DEFAULT_PORT = 9431
DEFAULT_USE_SSL = True
DEFAULT_VERIFY_SSL = False
DEFAULT_SCAN_INTERVAL = 300
MIN_SCAN_INTERVAL = 60

DATA_HOSTNAME = "hostname"
DATA_DISKS = "disks"
DATA_POOLS = "pools"
DATA_UNREADABLE = "unreadable"
DATA_COLLECTED_AT = "collected_at"
