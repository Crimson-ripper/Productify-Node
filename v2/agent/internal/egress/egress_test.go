package egress

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/netip"
	"strings"
	"testing"
)

func TestPublic(t *testing.T) {
	blocked := []string{
		"10.0.0.5", "172.16.0.1", "172.22.15.50", "172.27.96.1", "172.31.255.255", "192.168.1.1",
		"192.168.65.254", "127.0.0.1", "169.254.169.254", "100.64.0.1", "0.0.0.0", "224.0.0.1",
		"255.255.255.255", "::1", "fe80::1", "fd00::1", "::ffff:192.168.1.1", "::ffff:127.0.0.1", "198.18.0.1",
	}
	for _, s := range blocked {
		if Public(netip.MustParseAddr(s)) {
			t.Errorf("%s should be blocked", s)
		}
	}
	for _, s := range []string{"1.1.1.1", "8.8.8.8", "151.101.0.223", "2606:4700:4700::1111", "172.32.0.1", "172.15.0.1"} {
		if !Public(netip.MustParseAddr(s)) {
			t.Errorf("%s should be allowed", s)
		}
	}
}

// fakeNet: names resolve from a table; dials record the address and connect to a local echo server.
type fakeNet struct {
	names  map[string][]string
	dialed []string
	target string
}

func (f *fakeNet) resolve(_ context.Context, host string) ([]netip.Addr, error) {
	var out []netip.Addr
	for _, s := range f.names[host] {
		out = append(out, netip.MustParseAddr(s))
	}
	if out == nil {
		return nil, fmt.Errorf("no such host")
	}
	return out, nil
}

func (f *fakeNet) dial(ctx context.Context, network, addr string) (net.Conn, error) {
	f.dialed = append(f.dialed, addr)
	var d net.Dialer
	return d.DialContext(ctx, "tcp", f.target)
}

func newProxy(t *testing.T, names map[string][]string) (*fakeNet, *httptest.Server, *httptest.Server) {
	t.Helper()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, "hello from "+r.Host) }))
	f := &fakeNet{names: names, target: upstream.Listener.Addr().String()}
	px := httptest.NewServer(&Proxy{Resolve: f.resolve, Dial: f.dial})
	t.Cleanup(func() { px.Close(); upstream.Close() })
	return f, px, upstream
}

func connect(t *testing.T, proxyURL, dest string) (int, string) {
	t.Helper()
	c, err := net.Dial("tcp", strings.TrimPrefix(proxyURL, "http://"))
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	fmt.Fprintf(c, "CONNECT %s HTTP/1.1\r\nHost: %s\r\n\r\n", dest, dest)
	br := bufio.NewReader(c)
	resp, err := http.ReadResponse(br, nil)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		return resp.StatusCode, string(b)
	}
	// tunnel open: speak plain HTTP through it to the fake upstream
	fmt.Fprintf(c, "GET / HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n", dest)
	r2, err := http.ReadResponse(br, nil)
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(r2.Body)
	return 200, string(b)
}

func TestConnectAllowsPublic(t *testing.T) {
	f, px, _ := newProxy(t, map[string][]string{"pypi.org": {"151.101.0.223"}})
	code, body := connect(t, px.URL, "pypi.org:443")
	if code != 200 || !strings.Contains(body, "hello") {
		t.Fatalf("got %d %q", code, body)
	}
	if len(f.dialed) != 1 || f.dialed[0] != "151.101.0.223:443" {
		t.Fatalf("dialed %v; must dial the checked IP", f.dialed)
	}
}

func TestConnectBlocksLocalTargets(t *testing.T) {
	f, px, _ := newProxy(t, map[string][]string{
		"evil.example":   {"192.168.1.1"},     // DNS pointing at the LAN
		"mixed.example":  {"10.0.0.1"},        // private only
		"host.docker.internal": {"192.168.65.254"},
	})
	for _, dest := range []string{
		"172.22.15.50:445", "172.22.15.50:443", "172.27.96.1:443", "192.168.1.1:80", "127.0.0.1:443",
		"169.254.169.254:80", "[::1]:443", "evil.example:443", "mixed.example:443", "host.docker.internal:443",
		"1.1.1.1:22", "1.1.1.1:445",
	} {
		code, body := connect(t, px.URL, dest)
		if code != http.StatusForbidden {
			t.Errorf("%s: got %d %q, want 403", dest, code, body)
		}
	}
	if len(f.dialed) != 0 {
		t.Fatalf("must not dial blocked targets, dialed %v", f.dialed)
	}
}

func TestConnectSkipsPrivateAnswers(t *testing.T) {
	// A name with one private and one public answer: only the public one is used.
	f, px, _ := newProxy(t, map[string][]string{"cdn.example": {"10.1.2.3", "93.184.216.34"}})
	if code, _ := connect(t, px.URL, "cdn.example:443"); code != 200 {
		t.Fatalf("got %d", code)
	}
	if len(f.dialed) != 1 || f.dialed[0] != "93.184.216.34:443" {
		t.Fatalf("dialed %v", f.dialed)
	}
}

func TestPlainHTTP(t *testing.T) {
	f, px, _ := newProxy(t, map[string][]string{"example.com": {"93.184.216.34"}, "router.local": {"192.168.1.1"}})
	client := &http.Client{Transport: &http.Transport{Proxy: func(*http.Request) (*urlT, error) { return parse(px.URL) }}}
	resp, err := client.Get("http://example.com/")
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if resp.StatusCode != 200 || !strings.Contains(string(b), "hello") {
		t.Fatalf("got %d %q", resp.StatusCode, b)
	}
	resp, err = client.Get("http://router.local/")
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("LAN via plain http: got %d", resp.StatusCode)
	}
	if len(f.dialed) != 1 {
		t.Fatalf("dialed %v", f.dialed)
	}
}
