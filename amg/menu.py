""" Terminal menu code to browse tracks. """

import enum
import webbrowser

import cursesmenu

import amg


class AmgMenu(cursesmenu.CursesMenu):

    """Custom menu to choose review/track."""

    UserAction = enum.Enum("UserAction", ("DEFAULT", "OPEN_REVIEW", "DOWNLOAD_AUDIO"))

    def __init__(self, *, reviews, known_reviews, http_cache, mode, selected_idx):
        menu_subtitle = {amg.PlayerMode.MANUAL: "Select a track", amg.PlayerMode.RADIO: "Select track to start from"}
        super().__init__(
            f"AMG Player v{amg.__version__}",
            f"{mode.name.capitalize()} mode: {menu_subtitle[mode]} "
            "(ENTER to play, "
            "D to download audio, "
            "R to open review, "
            "Q to exit)",
            True,
        )
        if selected_idx is not None:
            self.current_option = selected_idx
        review_strings = __class__.reviewsToStrings(reviews, known_reviews, http_cache)
        for index, (review, review_string) in enumerate(zip(reviews, review_strings)):
            self.append_item(ReviewItem(review, review_string, index, self))

    def process_user_input(self):
        """
        Override key handling to add "open review" and "quick exit" features.

        See cursesmenu.CursesMenu.process_user_input
        """
        self.user_action = __class__.UserAction.DEFAULT
        c = super().process_user_input()
        if c in frozenset(map(ord, "rR")):
            self.user_action = __class__.UserAction.OPEN_REVIEW
            self.select()
        elif c in frozenset(map(ord, "dD")):
            # select last item (exit item)
            self.user_action = __class__.UserAction.DOWNLOAD_AUDIO
            self.select()
        elif c in frozenset(map(ord, "qQ")):
            # select last item (exit item)
            self.current_option = len(self.items) - 1
            self.select()

    def get_last_user_action(self):
        """Return last user action when item was selected."""
        return self.user_action

    @staticmethod
    def reviewsToStrings(reviews, known_reviews, http_cache):
        """Generate a list of string representations of reviews."""
        lines = []
        for i, review in enumerate(reviews):
            try:
                play_count = known_reviews.getPlayCount(review.url)
                played = (
                    f"Last played: {known_reviews.getLastPlayed(review.url).strftime('%x %H:%M')} "
                    f"({play_count} time{'s' if play_count > 1 else ''})"
                )
            except KeyError:
                if review.url in http_cache:
                    review_page = amg.fetch_page(review.url, http_cache=http_cache)
                    if amg.get_embedded_track(review_page, http_cache)[0] is None:
                        played = "No track"
                    else:
                        played = "Last played: never"
                else:
                    played = "Last played: never"
            lines.append((f"{review.artist} - {review.album}", played))
        # auto align/justify
        max_lens = [0] * len(lines[0])
        for line in lines:
            for i, s in enumerate(line):
                if len(s) > max_lens[i]:
                    max_lens[i] = len(s)
        sep = "\t"
        for i, line in enumerate(lines):
            lines[i] = "".join(
                (" " if i < 9 else "", sep.join(s.ljust(max_len + 1) for s, max_len in zip(line, max_lens)))
            )
        return lines

    @staticmethod
    def setupAndShow(mode, reviews, known_reviews, http_cache, selected_idx=None):
        """Set up and display interactive menu, return selected review index or None if exist requested."""
        menu = AmgMenu(
            reviews=reviews, known_reviews=known_reviews, http_cache=http_cache, mode=mode, selected_idx=selected_idx
        )
        menu.show()
        idx = menu.selected_option
        return None if (idx == len(reviews)) else (idx, menu.get_last_user_action())


class ReviewItem(cursesmenu.items.SelectionItem):

    """Custom menu item (menu line), overriden to support several actions per item."""

    def __init__(self, review, review_string, index, menu):
        super().__init__(review_string, index, menu)
        self.review = review

    def action(self):
        """React to user action."""
        if self.menu.get_last_user_action() is AmgMenu.UserAction.OPEN_REVIEW:
            webbrowser.open_new_tab(self.review.url)
            self.should_exit = False
        else:
            self.should_exit = True
