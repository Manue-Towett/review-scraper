import re
import json
import time
import dataclasses
from typing import Optional, Union, Tuple

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import *
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC

USER = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"

REVIEW_LINK = "https://www.google.com/maps/search/spain+hotels/@31.774513,-15.9297508,5z/data=!3m1!4b1?hl=en&entry=ttu"

MAPPINGS = {"1": "one_star",
            "2": "two_stars",
            "3": "three_stars",
            "4": "four_stars",
            "5": "five_stars"}

@dataclasses.dataclass
class Review:
    review_id: str
    author_link: str
    author_title: str
    author_id: str
    author_image: str
    review_text: str
    owner_answer: str
    owner_answer_timestamp: str
    owner_answer_timestamp_datetime_utc: str
    review_link: str
    review_rating: str
    review_timestamp: str
    review_datetime_utc: str
    review_likes: str
    review_img_url: Optional[list] = dataclasses.field(default_factory=list)

@dataclasses.dataclass
class Scores:
    one_star: str
    two_stars: str
    three_stars: str
    four_stars: str
    five_stars: str
    
@dataclasses.dataclass
class Place:
    name: str
    google_id: str
    rating: str
    reviews_total: str
    location_link: str
    reviews_link: Optional[str] = None
    reviews_id: Optional[str] = None
    reviews_per_score: Scores = None
    reviews: list[Review] = dataclasses.field(default_factory=list)

class GoogleMapsScraper:
    """Scrapes reviews from google maps"""
    def __init__(self) -> None:
        self.browser = self.__open_browser()

        self.author_re = re.compile(r"([\w\s'\-]+)\n.*?(\d+)\s*reviews?.*?\n(\d{1,2}/\d{1,2})\n([\w\s]+?ago)",
                                    flags=re.DOTALL|re.I)
        
        self.crawled = set()
        self.places: list[Place] = []

    @staticmethod
    def __open_browser() -> webdriver.Chrome:
        options = webdriver.ChromeOptions()

        options.add_argument("--disable-infobars")

        options.add_argument('--no-sandbox')

        options.add_argument('--start-maximized')

        options.add_argument('--ignore-gpu-blocklist')

        options.add_argument('--single-process')

        options.add_argument('--disable-dev-shm-usage')

        # options.add_argument("--headless=new")

        options.add_argument(f"user-agent={USER}")

        options.add_argument("--incognito")

        options.add_argument('--disable-blink-features=AutomationControlled')

        options.add_experimental_option('useAutomationExtension', False)

        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        options.add_argument("--log-level=3")

        options.add_argument('--disable-extensions')

        options.add_argument('--lang=en-GB')

        options.set_capability('pageLoadStrategy', 'none')

        chrome_service = Service()

        while True:
            try:
                browser = webdriver.Chrome(service=chrome_service, 
                                                options=options)

                browser.command_executor._commands["SEND_COMMAND"] = (
                    "POST", "/session/$sessionId/chromium/send_command"
                )
                
                return browser

            except:pass

    def __locate(self, 
                 selector: str, 
                 method: Optional[By]=By.CSS_SELECTOR, 
                 browser: Optional[WebElement]=None,
                 multiple: Optional[bool]=False,
                 breakout: Optional[bool]=False,
                 timeout: Optional[int]=None) -> Union[WebElement, list[WebElement], str]:
        if browser is None:
            browser = self.browser
        
        trials, time_taken = 0, 0

        while True:
            try:
                if multiple:
                    # return browser.find_elements(method, selector)
                    return WebDriverWait(browser, 10).until(
                        EC.presence_of_all_elements_located((method, selector))) #browser.find_elements(method, selector)
                else:
                    # return browser.find_element(method, selector)
                    return WebDriverWait(browser, 10).until(
                        EC.presence_of_element_located((method, selector)))
            
            except Exception as e: 
                if (trials == 3 and breakout) \
                    or (timeout is not None and time_taken >= timeout): return
                
                trials += 1

                time_taken += 10

                time.sleep(10)
                print(selector)

    def __load_page(self, url: str, new_tab: Optional[bool]=False) -> None:
        if not new_tab:
            self.browser.get(url)

            time.sleep(2)

        else:
            self.browser.execute_script('''window.open("{}","_blank");'''.format(url))

            time.sleep(1)

            self.browser.switch_to.window(self.browser.window_handles[1])

    def __scroll_down(self, container: WebElement) -> None:
        container.send_keys(Keys.END)

        time.sleep(5)

    def __get_review_text(self, review_element: WebElement) -> Tuple[str, str]:
        review_element.location_once_scrolled_into_view
    
        review_id = review_element.get_attribute("data-review-id")

        review_text_tag = self.__locate(browser=review_element,
                                        selector=f"div[id='{review_id}']")
        
        try:
            see_more = self.__locate('button[aria-label="See more"]',
                                     browser=review_text_tag, 
                                     breakout=True,
                                     timeout=10)
            
            see_more.click()

            time.sleep(1)

        except:pass

        review_text = review_text_tag.text

        return review_id, review_text

    def __get_rating_slugs(self, 
                           review_element: WebElement) -> Optional[Tuple[str, str, str]]:
        author_re = self.author_re.search(review_element.text)

        if not author_re: 
            print(review_element.text)
            return
        
        name = author_re.group(1)
        review_rating = author_re.group(3)
        review_posted = author_re.group(4)

        return name, review_rating, review_posted

    def __get_review_link(self, share_button: WebElement, button_text: str) -> str:
        if re.search(r"Share", button_text, re.I):
            print(button_text)

            while True:
                try:
                    share_button.location_once_scrolled_into_view
                    ActionChains(self.browser).move_to_element(share_button).perform()

                    share_button.click()

                    time.sleep(2)

                    input_tag = self.__locate('input[jsaction="pane.copyLink.clickInput"]')

                    review_link = None

                    while not review_link:
                        review_link = input_tag.get_attribute("value")

                    self.__locate(selector='button[aria-label="Close"]').click()
                    
                    time.sleep(2)

                    return review_link

                except: pass
    
    def __get_author_image_details(self, photo_button: WebElement) -> Optional[Tuple[str, str, str]]:
        aria_label = photo_button.get_attribute("aria-label")

        button_text = aria_label if aria_label else ""
        
        if re.search(r"photo\s+of", button_text, re.I):
            author_link: str = photo_button.get_attribute("data-href")

            image = self.__locate("img", method=By.TAG_NAME, browser=photo_button)

            author_image_link = image.get_attribute("src")

            author_id_re = re.search(r"contrib/(.+)/review", author_link)

            author_id = author_id_re.group(1)

            return author_id, author_link, author_image_link

    def __get_likes(self, likes_button: WebElement) -> Optional[str]:
        title = likes_button.get_attribute("title")

        title = title if title else ""

        likes_re = re.search(r"(\d*)\s*like", title, re.I)

        if likes_re:
            likes = likes_re.group(1)

            likes = likes if likes.strip() else "0"

            return likes

    def __get_review_photo(self, photo_button: WebElement) -> Optional[str]:
        photo_index = photo_button.get_attribute("data-photo-index")

        if photo_index:
            style: str = photo_button.get_attribute("style")

            image_re = re.search(r"(http.+)&quot;", style)

            if image_re:
                return image_re.group(1)

    def __get_owner_response(self, review_text: str) -> Tuple[str, str]:
        response_re = re.search(r"Response\s+from\s+the\s+owner\s*([\w\s]+ago)\s(.+)",
                                review_text,
                                flags=re.I|re.DOTALL)

        if response_re:
            owner_answer_timestamp = response_re.group(1)
            owner_answer = response_re.group(2)
        else:
            owner_answer_timestamp = ""
            owner_answer = ""

        return owner_answer, owner_answer_timestamp

    def __get_scores(self, place: Place) -> bool:
        found = False

        try:
            score_tags: list[WebElement] = self.__locate(
                "tr[role='img']", multiple=True, breakout=True
            )

            scores = {}

            for tag in score_tags:
                score_text: str = tag.get_attribute("aria-label")

                scores_re = re.search(r"(\d)\s*\w+,\s*([\d,]+)", score_text)

                scores[MAPPINGS[scores_re.group(1)]] = scores_re.group(2)
            
            place.reviews_per_score = Scores(**scores)

            found = True

        except:pass
    
        return found

    def __find_businesses(self) -> list[WebElement]:
        business_containers = self.__locate("div[role='feed']", multiple=True)

        for container in business_containers:
            aria_label = container.get_attribute("aria-label")

            print(aria_label)

            if aria_label and re.search(r"results", aria_label, re.I):
                business_container = container

        businesses_tags: list[WebElement] = self.__locate(
            "./*",
            method=By.XPATH,
            browser=business_container,
            multiple=True
        )

        start_found = False

        businesses: list[WebElement] = []

        for element in businesses_tags:
            try:
                if start_found and not element.get_attribute("class"):
                    businesses.append(element)

                if element.get_attribute("role") == "presentation":
                    start_found = True
            except:pass
        
        print(len(businesses_tags))

        return businesses

    def __scrape_places(self) -> list[Place]:
        places: list[Place] = []

        businesses = self.__find_businesses()

        for company in businesses:
            details = re.search(r"(.+?)\n(\d+\.?\d?)\s*\(([\d,]+)", 
                                company.text,
                                flags=re.I|re.DOTALL)

            if not details: continue

            name = details.group(1)

            rating = details.group(2)

            reviews = details.group(3)

            for link in company.find_elements(By.TAG_NAME, "a"):
                aria_label = link.get_attribute("aria-label")

                if re.search(rf'{name}', aria_label, flags=re.I):
                    place_link_tag = link

                    break

            location_link = place_link_tag.get_attribute("href")

            if location_link in self.crawled: continue

            jslog: str = place_link_tag.get_attribute("jslog")

            google_id_re = re.search(r"metadata:(.+)", jslog, re.I)

            google_id = google_id_re.group(1)

            place = Place(name=name, 
                          google_id=google_id,
                          rating=rating,
                          reviews_total=reviews,
                          location_link=location_link)
            
            places.append(place)
        
        return places
    
    def __process_review(self, review_tag: WebElement) -> Optional[Review]:
        review_id, review_text = self.__get_review_text(review_tag)

        rating_slugs = self.__get_rating_slugs(review_tag)

        if rating_slugs is not None:
            name, review_rating, review_posted = rating_slugs
        else:
            return

        buttons: list[WebElement] = self.__locate(
            browser=review_tag,
            multiple=True,
            selector=f'button[data-review-id="{review_id}"]'
        )

        review_images = []

        for button in buttons:
            author_slugs = self.__get_author_image_details(button)

            if author_slugs:
                author_id, author_link, author_image_link = author_slugs
            
            aria_label = button.get_attribute("aria-label")

            button_text = aria_label if aria_label else ""

            share_value = self.__get_review_link(button, button_text)                    

            if share_value:
                review_link = share_value
            
            likes_value = self.__get_likes(button)

            if likes_value:
                likes = likes_value

            photo = self.__get_review_photo(button)

            if photo:
                review_images.append(photo)

        owner_answer, owner_answer_timestamp = self.__get_owner_response(review_tag.text)

        review = Review(review_id=review_id,
                        author_link=author_link,
                        author_title=name,
                        author_id=author_id,
                        author_image=author_image_link,
                        review_text=review_text,
                        owner_answer=owner_answer,
                        owner_answer_timestamp=owner_answer_timestamp,
                        owner_answer_timestamp_datetime_utc=None,
                        review_link=review_link,
                        review_rating=review_rating,
                        review_timestamp=review_posted,
                        review_datetime_utc=None,
                        review_likes=likes)
        
        review.review_img_url.extend(review_images)
    
        return review

    def __process_places(self, 
                         places: list[Place], 
                         business_container: WebElement) -> None:
        for place in places:
            self.__load_page(place.location_link, new_tab=True)

            time.sleep(3)

            reviews_exist = self.__get_scores(place)

            if not reviews_exist: continue

            found = False

            while not found:
                buttons: list[WebElement] = self.__locate(
                    selector='button[role="tab"]',
                    multiple=True
                )

                for button in buttons:
                    aria_label = button.get_attribute("aria-label")
                    
                    if not aria_label or not re.search(r"reviews", aria_label, re.I): continue

                    ActionChains(self.browser).move_to_element(button).click(button).perform()

                    time.sleep(2)
                    
                    button.click()

                    found = True

                    break
                
            place.reviews_link = self.browser.current_url

            reviews_id_re = re.search(r"data=(.+)\?", place.reviews_link)

            place.reviews_id = reviews_id_re.group(1)

            refine_reviews = self.__locate('div[aria-label="Refine reviews"]')

            reviews_container = self.__locate(selector="..",
                                                method=By.XPATH,
                                                browser=refine_reviews)
            
            len_reviews, trials, crawled = 0, 0, []
            
            while True:
                self.__scroll_down(reviews_container)

                self.browser.switch_to.window(self.browser.window_handles[0])

                self.__scroll_down(business_container)

                self.browser.switch_to.window(self.browser.window_handles[1])

                review_tags = self.__locate(
                    selector='div[class="jftiEf fontBodyMedium "]',
                    multiple=True
                )

                if len(review_tags) == len_reviews \
                    or len(review_tags) >= 200:
                    if trials == 3 or len(review_tags) >= 200:
                        break

                    trials += 1

                    time.sleep(5)

                    continue

                len_reviews = len(review_tags)

                trials = 0
            
                for review_tag in review_tags:
                    if review_tag in crawled: continue

                    review = self.__process_review(review_tag)

                    if review is not None:
                        place.reviews.append(review)
                    
                    crawled.append(review_tag)

            self.browser.close()

            self.browser.switch_to.window(self.browser.window_handles[0])

            self.places.append(place)
    
    def __save(self, places: list[Place]) -> None:
        results: list[dict[str, str|dict|list[dict[str, str]]]] = []

        [results.append(dataclasses.asdict(place)) for place in places]

        with open("data.json", "w") as file:
            json.dump(results, file, indent=4)
        
        df_data = []

        business_keys = ["name", 
                         "google_id", 
                         "rating", 
                         "reviews_total", 
                         "location_link",
                         "reviews_link",
                         "reviews_id"]

        for result in results:
            business = {key:result[key] for key in business_keys}

            business.update(result["reviews_per_score"])
            
            [df_data.append({**business,  **review}) for review in result["reviews"]]
        
        df = pd.DataFrame(df_data)

        df.to_csv("data.csv", index=False)

    def run(self) -> None:
        with open("crawled.txt", "r") as file:
            [self.crawled.add(line.strip()) for line in file.readlines()]

        self.__load_page(REVIEW_LINK)

        time.sleep(2)

        feed = self.__locate("div[role='feed']")

        previous_len, trials = 0, 0

        while True:
            self.__scroll_down(feed)

            businesses = self.__locate('div[class="TFQHme "]', multiple=True)

            if len(businesses) == previous_len:
                if trials == 3:
                    break

                trials += 1

                time.sleep(5)
            
            trials, previous_len = 0, len(businesses)

            places = self.__scrape_places()

            self.__process_places(places, feed)

            self.__save(self.places)

            [self.crawled.add(place.location_link) for place in places]

            with open("crawled.txt", "w") as file:
                [file.write(f"{place.location_link}\n") for place in places]

if __name__ == "__main__":
    app = GoogleMapsScraper()
    app.run()