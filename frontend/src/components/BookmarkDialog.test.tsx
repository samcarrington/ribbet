import { render, screen, fireEvent } from "@testing-library/react";
import { BookmarkDialog } from "./BookmarkDialog";

describe("BookmarkDialog", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <BookmarkDialog open={false} onClose={vi.fn()} onSubmit={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders dialog when open", () => {
    render(<BookmarkDialog open={true} onClose={vi.fn()} onSubmit={vi.fn()} />);
    expect(screen.getByText("Create Bookmark")).toBeInTheDocument();
  });

  it("calls onSubmit with note text", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();
    render(<BookmarkDialog open={true} onClose={onClose} onSubmit={onSubmit} />);
    const textarea = screen.getByPlaceholderText(/what's noteworthy/i);
    fireEvent.change(textarea, { target: { value: "Important point" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onSubmit).toHaveBeenCalledWith("Important point");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("does not submit empty notes", () => {
    const onSubmit = vi.fn();
    render(<BookmarkDialog open={true} onClose={vi.fn()} onSubmit={onSubmit} />);
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("calls onClose when Cancel clicked", () => {
    const onClose = vi.fn();
    render(<BookmarkDialog open={true} onClose={onClose} onSubmit={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("clears stale note when dialog reopens", () => {
    const onSubmit = vi.fn();
    const onClose = vi.fn();

    const { rerender } = render(
      <BookmarkDialog open={true} onClose={onClose} onSubmit={onSubmit} />
    );

    // Type a note and submit it
    const textarea = screen.getByPlaceholderText(/what's noteworthy/i);
    fireEvent.change(textarea, { target: { value: "First note" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    // Close the dialog
    rerender(
      <BookmarkDialog open={false} onClose={onClose} onSubmit={onSubmit} />
    );

    // Reopen — note should be blank
    rerender(
      <BookmarkDialog open={true} onClose={onClose} onSubmit={onSubmit} />
    );

    const reopenedTextarea = screen.getByPlaceholderText(/what's noteworthy/i);
    expect((reopenedTextarea as HTMLTextAreaElement).value).toBe("");
  });

  it("clears note when dialog opens even if not previously submitted", () => {
    const { rerender } = render(
      <BookmarkDialog open={true} onClose={vi.fn()} onSubmit={vi.fn()} />
    );

    // Type a note but cancel
    const textarea = screen.getByPlaceholderText(/what's noteworthy/i);
    fireEvent.change(textarea, { target: { value: "Abandoned note" } });

    rerender(
      <BookmarkDialog open={false} onClose={vi.fn()} onSubmit={vi.fn()} />
    );
    rerender(
      <BookmarkDialog open={true} onClose={vi.fn()} onSubmit={vi.fn()} />
    );

    const reopenedTextarea = screen.getByPlaceholderText(/what's noteworthy/i);
    expect((reopenedTextarea as HTMLTextAreaElement).value).toBe("");
  });
});
