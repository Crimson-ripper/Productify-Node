package egress

import "net/url"

type urlT = url.URL

func parse(s string) (*url.URL, error) { return url.Parse(s) }
