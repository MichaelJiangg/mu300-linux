include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-mu300-speedtest
PKG_VERSION:=1.0.0
PKG_RELEASE:=13
PKG_BUILD_DEPENDS:=luci-base/host
LUCI_MENU_TIMESTAMP:=$(shell date -u -d "@$$((1767225600 + $(PKG_RELEASE)))" +%Y%m%d%H%M.%S)

include $(INCLUDE_DIR)/package.mk

define Package/luci-app-mu300-speedtest
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=MU300 network speed test
  DEPENDS:=+luci-base
  PKGARCH:=all
endef

define Package/luci-app-mu300-speedtest/description
  Browser network speed test for the MU300 LuCI interface.
endef

define Build/Compile
	$(STAGING_DIR_HOSTPKG)/bin/po2lmo ./po/zh_Hans/mu300-speedtest.po $(PKG_BUILD_DIR)/mu300-speedtest.zh-cn.lmo
endef

define Package/luci-app-mu300-speedtest/install
	$(INSTALL_DIR) $(1)/www
	$(CP) ./root/. $(1)/
	$(CP) ./htdocs/. $(1)/www/
	sh ./stage-assets.sh "$(1)" "$(ENGINE_SOURCE_DIR)"
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/i18n
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/mu300-speedtest.zh-cn.lmo $(1)/usr/lib/lua/luci/i18n/
endef

# SDK APK builds normalize archive mtimes. Set the revision's menu mtime after extraction.
define Package/luci-app-mu300-speedtest/postinst
#!/bin/sh
TZ=UTC touch -t "$(LUCI_MENU_TIMESTAMP)" "$${IPKG_INSTROOT}/usr/share/luci/menu.d/$(PKG_NAME).json"
endef

$(eval $(call BuildPackage,luci-app-mu300-speedtest))
