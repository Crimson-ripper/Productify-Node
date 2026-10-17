//go:build windows

package ipc

import (
	"context"
	"strings"
	"testing"
	"time"

	"golang.org/x/sys/windows"
)

// The pipe's DACL must grant only SYSTEM, Administrators and interactive users,
// and must not inherit anything (e.g. Everyone or Anonymous).
func TestPipeACL(t *testing.T) {
	name := testPipe()
	l, err := Listen(name)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go Serve(ctx, l, func(Request) (any, error) { return nil, nil }) // Accept makes an instance available
	time.Sleep(200 * time.Millisecond)

	sd, err := windows.GetNamedSecurityInfo(name, windows.SE_FILE_OBJECT, windows.DACL_SECURITY_INFORMATION)
	if err != nil {
		t.Fatal(err)
	}
	got := sd.String()
	if !strings.Contains(got, "D:P") {
		t.Errorf("DACL is not protected from inheritance: %s", got)
	}
	aces := got[strings.Index(got, "D:P")+3:]
	for _, ace := range strings.Split(strings.Trim(aces, "()"), ")(") {
		sid := ace[strings.LastIndex(ace, ";")+1:]
		switch sid {
		case "SY", "BA":
		case "IU":
			if strings.Contains(ace, "GA") || strings.Contains(ace, "FA") {
				t.Errorf("interactive users must not get full control: %s", ace)
			}
		default:
			t.Errorf("unexpected principal %q in pipe ACL: %s", sid, got)
		}
	}
}
