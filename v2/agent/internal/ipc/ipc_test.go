package ipc

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"testing"
	"time"
)

func testPipe() string { return fmt.Sprintf(`\\.\pipe\productify-node-test-%d`, time.Now().UnixNano()) }

func TestRoundTripAndErrors(t *testing.T) {
	name := testPipe()
	l, err := Listen(name)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go Serve(ctx, l, func(r Request) (any, error) {
		if r.Op == "boom" {
			return nil, errors.New("nope")
		}
		return map[string]string{"echo": r.Op}, nil
	})

	c, err := Dial(name)
	if err != nil {
		t.Fatal(err)
	}
	data, err := Call(c, Request{Op: "status"})
	if err != nil {
		t.Fatal(err)
	}
	var got map[string]string
	_ = json.Unmarshal(data, &got)
	if got["echo"] != "status" {
		t.Errorf("got %v", got)
	}

	c, _ = Dial(name)
	if _, err := Call(c, Request{Op: "boom"}); err == nil || err.Error() != "nope" {
		t.Errorf("handler error not returned: %v", err)
	}
}

func TestSecondListenerCannotTakeOver(t *testing.T) {
	name := testPipe()
	l, err := Listen(name)
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	if l2, err := Listen(name); err == nil {
		l2.Close()
		t.Fatal("a second process could listen on the agent's pipe")
	}
}
