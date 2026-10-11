/*
 * mu300-voice-events: serve mu300-voice's call events on a unix socket (docs/voice-api.md).
 *
 *   mu300-voice-events SOCKET FEED SNAPSHOT [GROUP]
 *
 * mu300-voice watch appends one JSON object per line to FEED (/run/mu300-voice/events.jsonl) and keeps the
 * current state in SNAPSHOT (state.json). This follows FEED and hands every new line to every connected reader;
 * a reader that connects first gets SNAPSHOT, so it never has to ask what is going on now.
 *
 * Read-only by design: nothing a client writes is ever interpreted (it is read and dropped, so a client cannot
 * fill a buffer either). The commands are mu300-voice's, with their own checks; this only tells.
 *
 * Who may connect is the socket file's mode: 0660 root:GROUP with GROUP, 0600 without - no network, no other
 * check. A reader that does not keep up (its socket buffer full) is dropped rather than waited for, so one stuck
 * client never delays the others or the watch. FEED moving to FEED.1 (mu300-voice rotates it at a size) is
 * followed: the old file is read to its end before the new one is opened.
 *
 * No libraries beyond libc and plain poll(): it builds static for the device (build.sh), and with any cc for the
 * tests (tests/test_voice_api.py).
 */
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#define MAX_CLIENTS 16
#define LINE_MAX_LEN 4096
#define TICK_MS 100

static int clients[MAX_CLIENTS];
static int nclients;
static volatile sig_atomic_t stop;
static const char *sock_path;

static void on_signal(int sig) { (void)sig; stop = 1; }

static void drop(int i)
{
	close(clients[i]);
	clients[i] = clients[--nclients];
}

/* the whole line or the client goes: a partial line would corrupt the stream for it */
static int send_all(int fd, const char *buf, size_t len)
{
	while (len > 0) {
		ssize_t n = send(fd, buf, len, MSG_DONTWAIT);
		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			return -1;
		buf += n;
		len -= (size_t)n;
	}
	return 0;
}

static void broadcast(const char *line, size_t len)
{
	for (int i = 0; i < nclients;) {
		if (send_all(clients[i], line, len) < 0)
			drop(i);
		else
			i++;
	}
}

static void send_snapshot(int fd, const char *path)
{
	char buf[LINE_MAX_LEN * 4];
	int f = open(path, O_RDONLY);
	if (f < 0)
		return;
	ssize_t n = read(f, buf, sizeof buf - 1);
	close(f);
	if (n <= 0)
		return;
	if (buf[n - 1] != '\n')
		buf[n++] = '\n';
	(void)send_all(fd, buf, (size_t)n);
}

/* the feed: complete lines go out, a partial last line waits for its end */
static char pend[LINE_MAX_LEN];
static size_t npend;

static void feed_bytes(const char *p, size_t n)
{
	for (size_t i = 0; i < n; i++) {
		if (npend < sizeof pend)
			pend[npend++] = p[i];
		if (p[i] == '\n') {
			/* an over-long line is dropped whole, never cut */
			if (npend < sizeof pend || pend[sizeof pend - 1] == '\n')
				broadcast(pend, npend);
			npend = 0;
		} else if (npend == sizeof pend) {
			pend[sizeof pend - 1] = 0; /* mark: too long, skip to the next newline */
		}
	}
}

static void drain(int fd)
{
	char buf[4096];
	ssize_t n;
	while ((n = read(fd, buf, sizeof buf)) > 0)
		feed_bytes(buf, (size_t)n);
}

static int listen_on(const char *path, const char *group)
{
	struct sockaddr_un a;
	if (strlen(path) >= sizeof a.sun_path) {
		fprintf(stderr, "mu300-voice-events: socket path too long\n");
		return -1;
	}
	int s = socket(AF_UNIX, SOCK_STREAM, 0);
	if (s < 0)
		return -1;
	memset(&a, 0, sizeof a);
	a.sun_family = AF_UNIX;
	strcpy(a.sun_path, path);
	unlink(path);
	/* created owner-only, opened to the group after: never a moment with wider access */
	mode_t old = umask(0177);
	int r = bind(s, (struct sockaddr *)&a, sizeof a);
	umask(old);
	if (r < 0 || listen(s, 8) < 0) {
		perror("mu300-voice-events: bind");
		close(s);
		return -1;
	}
	if (group && *group) {
		struct group *g = getgrnam(group);
		if (!g || chown(path, (uid_t)-1, g->gr_gid) < 0 || chmod(path, 0660) < 0)
			fprintf(stderr, "mu300-voice-events: group %s not applied, the socket stays 0600\n", group);
	}
	return s;
}

int main(int argc, char **argv)
{
	if (argc < 4 || argc > 5) {
		fprintf(stderr, "usage: mu300-voice-events SOCKET FEED SNAPSHOT [GROUP]\n");
		return 2;
	}
	sock_path = argv[1];
	const char *feed = argv[2], *snapshot = argv[3], *group = argc == 5 ? argv[4] : NULL;

	signal(SIGPIPE, SIG_IGN);
	signal(SIGTERM, on_signal);
	signal(SIGINT, on_signal);

	int ls = listen_on(sock_path, group);
	if (ls < 0)
		return 1;
	fcntl(ls, F_SETFL, O_NONBLOCK);

	/* start at the feed's end: what came before is in the snapshot */
	int ff = open(feed, O_RDONLY);
	struct stat st, cur;
	if (ff >= 0) {
		lseek(ff, 0, SEEK_END);
		fstat(ff, &cur);
	}

	while (!stop) {
		struct pollfd p[MAX_CLIENTS + 1];
		p[0].fd = ls;
		p[0].events = POLLIN;
		for (int i = 0; i < nclients; i++) {
			p[i + 1].fd = clients[i];
			p[i + 1].events = POLLIN;
		}
		int n = poll(p, (nfds_t)nclients + 1, TICK_MS);
		if (n < 0 && errno != EINTR)
			break;
		if (n > 0) {
			/* clients: input is dropped unread in meaning; hang-ups are noticed here */
			for (int i = nclients - 1; i >= 0; i--) {
				if (!(p[i + 1].revents & (POLLIN | POLLHUP | POLLERR)))
					continue;
				char junk[256];
				ssize_t r = recv(clients[i], junk, sizeof junk, MSG_DONTWAIT);
				if (r == 0 || (r < 0 && errno != EAGAIN && errno != EINTR))
					drop(i);
			}
			if (p[0].revents & POLLIN) {
				int c;
				while ((c = accept(ls, NULL, NULL)) >= 0) {
					if (nclients == MAX_CLIENTS) {
						close(c);
						continue;
					}
					send_snapshot(c, snapshot);
					clients[nclients++] = c;
				}
			}
		}
		/* the feed: new lines, then has it moved (rotated) or appeared? */
		if (ff >= 0)
			drain(ff);
		if (stat(feed, &st) == 0) {
			if (ff < 0 || st.st_ino != cur.st_ino || st.st_dev != cur.st_dev) {
				if (ff >= 0) {
					drain(ff); /* the rest of the old one first */
					close(ff);
				}
				npend = 0;
				ff = open(feed, O_RDONLY);
				if (ff >= 0) {
					fstat(ff, &cur);
					drain(ff);
				}
			} else if (st.st_size < lseek(ff, 0, SEEK_CUR)) {
				lseek(ff, 0, SEEK_SET); /* truncated in place */
				npend = 0;
			}
		}
	}
	unlink(sock_path);
	return 0;
}
