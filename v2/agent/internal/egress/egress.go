// Package egress is the only way a renter job reaches the network.
//
// Job containers sit on an internal Docker network with no route anywhere:
// not the internet, not the provider's LAN, not the provider's own computer.
// A small HTTP(S) proxy (this package, run as productify-egress in its own
// container) is the one door out, and it only connects to public internet
// addresses. Hostnames are resolved here and the connection is made to the
// checked IP, so DNS tricks can't point a public-looking name at a local one.
package egress

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/netip"
	"strconv"
	"strings"
	"sync"
	"time"
)

// AllowedPorts are the destination ports renters may use (web traffic: pip,
// conda, Hugging Face, git over https).
var AllowedPorts = map[int]bool{80: true, 443: true}

var blockedPrefixes = func() []netip.Prefix {
	var out []netip.Prefix
	for _, s := range []string{
		"0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
		"172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15",
		"198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
		"::/128", "::1/128", "64:ff9b:1::/48", "100::/64", "2001:db8::/32", "fc00::/7", "fe80::/10", "ff00::/8",
	} {
		out = append(out, netip.MustParsePrefix(s))
	}
	return out
}()

// Public reports whether ip is an ordinary internet address a job may reach.
func Public(ip netip.Addr) bool {
	ip = ip.Unmap() // ::ffff:192.168.1.1 is still 192.168.1.1
	if !ip.IsValid() || ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() ||
		ip.IsLinkLocalMulticast() || ip.IsMulticast() || ip.IsUnspecified() || ip.IsInterfaceLocalMulticast() {
		return false
	}
	for _, p := range blockedPrefixes {
		if p.Contains(ip) {
			return false
		}
	}
	return true
}

// Resolver looks up a host's addresses. Tests replace it.
type Resolver func(ctx context.Context, host string) ([]netip.Addr, error)

func systemResolver(ctx context.Context, host string) ([]netip.Addr, error) {
	return net.DefaultResolver.LookupNetIP(ctx, "ip", host)
}

// ErrBlocked means the destination isn't a public internet address or port.
var ErrBlocked = errors.New("destination not allowed")

// Proxy is an HTTP proxy that supports CONNECT (https) and plain http.
type Proxy struct {
	Resolve Resolver
	Dial    func(ctx context.Context, network, addr string) (net.Conn, error)
	Log     *slog.Logger
	MaxConn int

	once sync.Once
	sem  chan struct{}
}

func (p *Proxy) init() {
	p.once.Do(func() {
		if p.Resolve == nil {
			p.Resolve = systemResolver
		}
		if p.Dial == nil {
			d := &net.Dialer{Timeout: 15 * time.Second, KeepAlive: 30 * time.Second}
			p.Dial = d.DialContext
		}
		if p.Log == nil {
			p.Log = slog.New(slog.NewTextHandler(io.Discard, nil))
		}
		if p.MaxConn <= 0 {
			p.MaxConn = 256
		}
		p.sem = make(chan struct{}, p.MaxConn)
	})
}

// dialChecked resolves hostport and connects to the first public address.
func (p *Proxy) dialChecked(ctx context.Context, hostport string) (net.Conn, error) {
	host, portStr, err := net.SplitHostPort(hostport)
	if err != nil {
		return nil, fmt.Errorf("%w: bad address", ErrBlocked)
	}
	port, err := strconv.Atoi(portStr)
	if err != nil || !AllowedPorts[port] {
		return nil, fmt.Errorf("%w: port %s", ErrBlocked, portStr)
	}
	var addrs []netip.Addr
	if ip, err := netip.ParseAddr(strings.Trim(host, "[]")); err == nil {
		addrs = []netip.Addr{ip}
	} else {
		rctx, cancel := context.WithTimeout(ctx, 10*time.Second)
		addrs, err = p.Resolve(rctx, host)
		cancel()
		if err != nil {
			return nil, fmt.Errorf("can't resolve %s", host)
		}
	}
	var lastErr error = fmt.Errorf("%w: %s is not a public internet address", ErrBlocked, host)
	for _, ip := range addrs {
		if !Public(ip) {
			continue
		}
		c, err := p.Dial(ctx, "tcp", netip.AddrPortFrom(ip.Unmap(), uint16(port)).String())
		if err == nil {
			return c, nil
		}
		lastErr = err
	}
	return nil, lastErr
}

func (p *Proxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	p.init()
	select {
	case p.sem <- struct{}{}:
		defer func() { <-p.sem }()
	default:
		http.Error(w, "too many connections", http.StatusServiceUnavailable)
		return
	}
	if r.Method == http.MethodConnect {
		p.connect(w, r)
		return
	}
	p.forward(w, r)
}

func refuse(w http.ResponseWriter, err error) {
	if errors.Is(err, ErrBlocked) {
		http.Error(w, "Productify: "+err.Error()+". Jobs can only reach public internet addresses on ports 80 and 443.", http.StatusForbidden)
		return
	}
	http.Error(w, "Productify: "+err.Error(), http.StatusBadGateway)
}

func (p *Proxy) connect(w http.ResponseWriter, r *http.Request) {
	up, err := p.dialChecked(r.Context(), r.Host)
	if err != nil {
		p.Log.Info("refused", "dest", r.Host, "err", err)
		refuse(w, err)
		return
	}
	defer up.Close()
	hj, ok := w.(http.Hijacker)
	if !ok {
		http.Error(w, "unsupported", http.StatusInternalServerError)
		return
	}
	down, buf, err := hj.Hijack()
	if err != nil {
		return
	}
	defer down.Close()
	_, _ = down.Write([]byte("HTTP/1.1 200 Connection established\r\n\r\n"))
	done := make(chan struct{}, 2)
	go func() { _, _ = io.Copy(up, buf); closeWrite(up); done <- struct{}{} }()
	go func() { _, _ = io.Copy(down, up); closeWrite(down); done <- struct{}{} }()
	<-done
	<-done
}

func closeWrite(c net.Conn) {
	if cw, ok := c.(interface{ CloseWrite() error }); ok {
		_ = cw.CloseWrite()
	}
}

var hopHeaders = []string{"Connection", "Proxy-Connection", "Keep-Alive", "Proxy-Authenticate",
	"Proxy-Authorization", "Te", "Trailer", "Transfer-Encoding", "Upgrade"}

func (p *Proxy) forward(w http.ResponseWriter, r *http.Request) {
	if r.URL.Scheme != "http" || r.URL.Host == "" {
		http.Error(w, "Productify: send a proxy request (absolute http:// URL) or CONNECT", http.StatusBadRequest)
		return
	}
	hostport := r.URL.Host
	if _, _, err := net.SplitHostPort(hostport); err != nil {
		hostport = net.JoinHostPort(hostport, "80")
	}
	tr := &http.Transport{
		Proxy:                 nil,
		DialContext:           func(ctx context.Context, _, _ string) (net.Conn, error) { return p.dialChecked(ctx, hostport) },
		ResponseHeaderTimeout: 60 * time.Second,
		DisableKeepAlives:     true,
	}
	out := r.Clone(r.Context())
	out.RequestURI = ""
	for _, h := range hopHeaders {
		out.Header.Del(h)
	}
	resp, err := tr.RoundTrip(out)
	if err != nil {
		var be error = err
		if !errors.Is(err, ErrBlocked) {
			be = errors.New("upstream request failed")
		}
		p.Log.Info("refused", "dest", hostport, "err", err)
		refuse(w, be)
		return
	}
	defer resp.Body.Close()
	for _, h := range hopHeaders {
		resp.Header.Del(h)
	}
	for k, vs := range resp.Header {
		for _, v := range vs {
			w.Header().Add(k, v)
		}
	}
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}

// ListenAndServe runs the proxy on addr until ctx ends.
func (p *Proxy) ListenAndServe(ctx context.Context, addr string) error {
	srv := &http.Server{Addr: addr, Handler: p, ReadHeaderTimeout: 30 * time.Second}
	go func() { <-ctx.Done(); _ = srv.Close() }()
	err := srv.ListenAndServe()
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return err
}
