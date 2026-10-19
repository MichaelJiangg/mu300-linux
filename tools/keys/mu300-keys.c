/*
 * mu300-keys: the device's buttons as lines of text, for mu300-buttons (a shell script: OpenWrt has no Python and
 * a pipe from od is block-buffered, so the events came too late).
 *
 * Watches every /dev/input/event* that has keys and prints, flushed at once:
 *   <code> short      released before the long-press time
 *   <code> long       still held when the long-press time is reached (once; nothing on its release)
 *   0 tick            every -t seconds (the LED timeout of mu300-buttons runs on these)
 * Codes are Linux key codes: 116 KEY_POWER, 138 the U30 Air's Wi-Fi key, 114/115 volume.
 *
 * usage: mu300-keys [-l MS] [-t SEC]   (long press: MS milliseconds, default 3000; tick: none by default)
 * SPDX-License-Identifier: MIT
 */
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <linux/netlink.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define MAXDEV 16
#define MAXKEY KEY_MAX

static long long now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000LL + ts.tv_nsec / 1000000;
}

static int has_keys(int fd)
{
	unsigned long ev = 0;
	if (ioctl(fd, EVIOCGBIT(0, sizeof(ev)), &ev) < 0)
		return 0;
	return (ev >> EV_KEY) & 1;
}

/* Charger-only boot: wait on input and kernel power-supply events, without a
 * periodic SOC/USB poll. Return 0 for power-on, 3 for unplug, 1 on unavailable
 * hardware (the caller continues normal boot rather than trapping the user). */
static int charge_online(const char *path)
{
	char value[8];
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return -1;
	ssize_t n = read(fd, value, sizeof(value));
	close(fd);
	if (n < 1 || (value[0] != '0' && value[0] != '1') ||
	    (n > 1 && value[1] != '\n'))
		return -1;
	return value[0] - '0';
}

static int charge_event(const char *buf, size_t size)
{
	for (size_t i = 0; i < size;) {
		size_t n = strnlen(buf + i, size - i);
		if (n == size - i)
			return 0;
		if (!strcmp(buf + i, "SUBSYSTEM=power_supply"))
			return 1;
		i += n + 1;
	}
	return 0;
}

static int charge_wait(struct pollfd *keys, int n, int events,
		       const char *online_path, long long hold)
{
	struct pollfd fds[MAXDEV + 1];
	long long down[MAXDEV] = {0}, unplug = 0;
	memcpy(fds, keys, n * sizeof(*keys));
	fds[n] = (struct pollfd){ .fd = events, .events = POLLIN };
	for (int i = 0; i < n; i++) {
		unsigned long bits[KEY_MAX / (8 * sizeof(unsigned long)) + 1] = {0};
		if (ioctl(fds[i].fd, EVIOCGKEY(sizeof(bits)), bits) >= 0 &&
		    (bits[KEY_POWER / (8 * sizeof(unsigned long))] >>
		     (KEY_POWER % (8 * sizeof(unsigned long))) & 1))
			down[i] = now_ms();
	}
	int changed = 1;
	for (;;) {
		long long now = now_ms();
		if (changed || unplug) {
			int online = charge_online(online_path);
			if (online < 0)
				return 1;
			if (online)
				unplug = 0;
			else if (!unplug)
				unplug = now;
			else if (now - unplug >= 500)
				return 3;
			changed = 0;
		}
		long long timeout = unplug ? unplug + 500 - now : -1;
		for (int i = 0; i < n; i++) {
			if (!down[i])
				continue;
			long long left = down[i] + hold - now;
			if (left <= 0)
				return 0;
			if (timeout < 0 || left < timeout)
				timeout = left;
		}
		if (poll(fds, n + 1, timeout) < 0) {
			if (errno == EINTR)
				continue;
			return 1;
		}
		for (int i = 0; i < n; i++)
			if (fds[i].revents & (POLLERR | POLLHUP | POLLNVAL))
				return 1;
		if (fds[n].revents & (POLLHUP | POLLNVAL))
			return 1;
		if (fds[n].revents & (POLLIN | POLLERR)) {
			char buf[8192];
			struct sockaddr_nl sender = {0};
			socklen_t len = sizeof(sender);
			ssize_t size = recvfrom(events, buf, sizeof(buf), MSG_DONTWAIT,
						(struct sockaddr *)&sender, &len);
			if (size < 0 && errno == ENOBUFS) {
				changed = 1;  /* lost notification: read the actual supply again */
				continue;
			}
			if (size < 0 && errno != EINTR && errno != EAGAIN)
				return 1;
			if (size > 0 && sender.nl_family == AF_NETLINK && !sender.nl_pid &&
			    charge_event(buf, size))
				changed = 1;
		}
		for (int i = 0; i < n; i++) {
			if (!(fds[i].revents & POLLIN))
				continue;
			struct input_event ev[16];
			ssize_t size = read(fds[i].fd, ev, sizeof(ev));
			if (size <= 0 || size % sizeof(ev[0]))
				return 1;
			for (int j = 0; j < size / (ssize_t)sizeof(ev[0]); j++) {
				if (ev[j].type != EV_KEY || ev[j].code != KEY_POWER)
					continue;
				if (ev[j].value == 1)
					down[i] = now_ms();
				else if (ev[j].value == 0)
					down[i] = 0;
			}
		}
	}
}

int main(int argc, char **argv)
{
	long long hold = 3000, tick = 0, next_tick = 0;
	static long long down[MAXKEY + 1];	/* press time, 0: not held */
	static char reported[MAXKEY + 1];	/* "long" already printed for this press */
	struct pollfd pfd[MAXDEV];
	int n = 0, opt, charging = 0;

	while ((opt = getopt(argc, argv, "cl:t:")) != -1) {
		if (opt == 'c')
			charging = 1;
		else if (opt == 'l')
			hold = atoll(optarg);
		else if (opt == 't')
			tick = atoll(optarg) * 1000;
		else {
			fprintf(stderr, "usage: mu300-keys [-c] [-l MS] [-t SEC]\n");
			return 2;
		}
	}

	DIR *d = opendir("/dev/input");
	struct dirent *e;
	while (d && (e = readdir(d)) && n < MAXDEV) {
		char path[300];
		if (strncmp(e->d_name, "event", 5))
			continue;
		snprintf(path, sizeof(path), "/dev/input/%s", e->d_name);
		int fd = open(path, O_RDONLY | O_CLOEXEC);
		if (fd < 0)
			continue;
		if (!has_keys(fd)) {
			close(fd);
			continue;
		}
		if (charging) {
			unsigned long bits[KEY_MAX / (8 * sizeof(unsigned long)) + 1] = {0};
			if (ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(bits)), bits) < 0 ||
			    !(bits[KEY_POWER / (8 * sizeof(unsigned long))] >>
			      (KEY_POWER % (8 * sizeof(unsigned long))) & 1)) {
				close(fd);
				continue;
			}
		}
		pfd[n].fd = fd;
		pfd[n].events = POLLIN;
		n++;
	}
	if (d)
		closedir(d);
	if (!n) {
		fprintf(stderr, "mu300-keys: no input device with keys\n");
		return 1;
	}
	if (charging) {
		int fd = socket(AF_NETLINK, SOCK_DGRAM | SOCK_CLOEXEC, NETLINK_KOBJECT_UEVENT);
		struct sockaddr_nl addr = { .nl_family = AF_NETLINK, .nl_groups = 1 };
		if (fd < 0 || bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
			return 1;
		int buffer = 256 * 1024;
		setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &buffer, sizeof(buffer));
		return charge_wait(pfd, n, fd, "/sys/class/power_supply/bq256xx-charger/online", hold);
	}
	setvbuf(stdout, NULL, _IOLBF, 0);
	if (tick > 0)
		next_tick = now_ms() + tick;

	for (;;) {
		/* wake up in time to report a long press while the key is still held */
		int timeout = -1;
		long long t = now_ms();
		for (int k = 0; k <= MAXKEY; k++) {
			if (down[k] && !reported[k]) {
				long long left = down[k] + hold - t;
				if (left < 0)
					left = 0;
				if (timeout < 0 || left < timeout)
					timeout = (int)left;
			}
		}
		if (tick > 0) {
			long long left = next_tick - t;
			if (left < 0)
				left = 0;
			if (timeout < 0 || left < timeout)
				timeout = (int)left;
		}
		if (poll(pfd, n, timeout) < 0 && errno != EINTR)
			return 1;
		t = now_ms();
		if (tick > 0 && t >= next_tick) {
			printf("0 tick\n");
			next_tick = t + tick;
		}
		for (int k = 0; k <= MAXKEY; k++) {
			if (down[k] && !reported[k] && t - down[k] >= hold) {
				printf("%d long\n", k);
				reported[k] = 1;
			}
		}
		for (int i = 0; i < n; i++) {
			if (!(pfd[i].revents & POLLIN))
				continue;
			struct input_event ev[16];
			ssize_t r = read(pfd[i].fd, ev, sizeof(ev));
			if (r <= 0)
				continue;
			for (int j = 0; j < (int)(r / sizeof(ev[0])); j++) {
				int k = ev[j].code;
				if (ev[j].type != EV_KEY || k > MAXKEY)
					continue;
				if (ev[j].value == 1) {		/* press */
					down[k] = t;
					reported[k] = 0;
				} else if (ev[j].value == 0 && down[k]) {	/* release */
					if (!reported[k])
						printf("%d short\n", k);
					down[k] = 0;
				}
			}
		}
	}
}
