################################################################################
#
# dashboard-display
#
################################################################################

DASHBOARD_DISPLAY_VERSION = 1.0
DASHBOARD_DISPLAY_SITE = $(BR2_EXTERNAL_DASHBOARD_PATH)/package/dashboard-display/src
DASHBOARD_DISPLAY_SITE_METHOD = local
DASHBOARD_DISPLAY_LICENSE = MIT
DASHBOARD_DISPLAY_DEPENDENCIES = qt6base qt6declarative host-qt6base
DASHBOARD_DISPLAY_CONF_OPTS = -DQT_HOST_PATH=$(HOST_DIR)

$(eval $(cmake-package))
