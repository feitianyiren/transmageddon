ACLOCAL_AMFLAGS = -I common/m4 ${ACLOCAL_FLAGS}

SUBDIRS	= bin src common po profiles presets appdata icons

@INTLTOOL_DESKTOP_RULE@

desktopdir = $(datadir)/applications
desktop_in_files = transmageddon.desktop.in.in
desktop_DATA = $(desktop_in_files:.desktop.in.in=.desktop)

man_MANS = transmageddon.1

transmageddondir = $(datadir)/transmageddon

EXTRA_DIST = \
	transmageddon.spec \
	transmageddon.spec.in \
	ChangeLog \
	autogen.sh \
	NEWS \
	AUTHORS \
	RELEASE \
	ABOUT-NLS \
        transmageddon.1 \
	$(desktop_in_files) \
	$(INTLTOOL)


DISTCLEANFILES =                \
        intltool-extract        \
        intltool-merge          \
        intltool-update		\
	autoregen.sh		\
	config.log		\
	Makefile		\
	Makefile.in		\
	missing			\
	mkinstalldirs		\
	py-compile		\
	config.status		\
	install-sh		\
	configure \
	$(desktop_DATA)


EXTRA_DIST +=                    \
        intltool-extract.in     \
        intltool-merge.in       \
        intltool-update.in	\
	TODO

DISTCHECK_CONFIGURE_FLAGS = \
       --enable-appdata-check

locale-uninstalled:
	if test -d po; then \
	    $(MAKE) -C po datadir=../$(top_builddir) install; \
	fi

locale-uninstalled-clean:
	@-rm -rf _trial_temp
	@-rm -rf $(top_builddir)/locale


all-local: locale-uninstalled
clean-local: locale-uninstalled-clean
