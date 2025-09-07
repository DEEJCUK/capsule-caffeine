#!/usr/bin/env python3
"""
Standalone scraper for Nespresso capsules.
Run: python scraper.py --output data.json
"""
import sys
import argparse
import json
import re
import logging
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from bs4 import BeautifulSoup

domain = "https://nespresso.com"

# Configure session with retries
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))


def get_json_from_page_with_query(url, selector, timeout=10):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    resp = session.get(url, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch URL: {url}, Status Code: {resp.status_code}"
        )
    soup = BeautifulSoup(resp.content, "html.parser")
    tags = soup.select(selector)
    if not tags:
        raise RuntimeError(f"Selector '{selector}' not found on the page: {url}")
    tag = str(tags[0])
    json_string = tag[tag.find("{") : tag.rfind("}") + 1]
    return json.loads(json_string)


def get_main_list(start_url):
    main_list = get_json_from_page_with_query(
        start_url,
        "div[id^=respProductListPLPCapsule]+script",
    )
    products = (
        main_list.get("configuration", {}).get("eCommerceData", {}).get("products", [])
    )
    if not products:
        raise RuntimeError("No products found in the JSON data.")
    categories = (
        main_list.get("configuration", {})
        .get("eCommerceData", {})
        .get("categories", [])
    )
    excluded_range_ids = [
        "nesclub2.tw.b2c/cat/capsule-range-limited-edition-b2c",
        "nesclub2.tw.b2c/cat/capsule-range-assortment",
    ]
    capsule_ranges = [
        x
        for x in categories
        if ("nesclub2.tw.b2c/cat/capsule-range" in x.get("superCategories", ""))
        and x.get("id") not in excluded_range_ids
    ]
    return main_list, products, categories, capsule_ranges


def extract_simple_data(domain, products, capsule_ranges):
    simple_data = {}
    for range_ in capsule_ranges:
        logging.info("Current range: %s", range_.get("name"))
        range_items = {}
        items = [
            x
            for x in products
            if range_.get("id") in x.get("ranges", [])
            and x.get("type") == "capsule"
            and x.get("unitQuantity") == 1
        ]
        for item in items:
            logging.info("Current capsule: %s", item.get("name"))
            url = domain + item.get("url", "")
            try:
                item_info = get_json_from_page_with_query(
                    url, "div[id^=respProductDetailPDPCapsule]+script"
                )
            except Exception as e:
                logging.warning("Failed to fetch item page %s: %s", url, e)
                continue
            product = (
                item_info.get("configuration", {})
                .get("eCommerceData", {})
                .get("product", {})
            )
            description = [x.get("text", "") for x in product.get("ingredients", [])]
            caffeine_matches = re.findall(r"(\d+)\s?mg", str(description))
            caffeine_mg = int(caffeine_matches[0]) if caffeine_matches else None
            image_url = domain + product.get("image", {}).get("url", "")
            range_items[product.get("name", "Unknown")] = {
                "caffeine_mg": caffeine_mg,
                "image_url": image_url,
            }
        simple_data[range_.get("name", "Unknown Range")] = range_items
    return simple_data


def save_data(simple_data, output_path):
    with open(output_path, "w", encoding="utf-8") as outfile:
        json.dump(simple_data, outfile, ensure_ascii=False, indent=2)
    logging.info("Saved data to %s", output_path)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Scrape Nespresso capsules and save simplified JSON."
    )
    parser.add_argument(
        "--url",
        "-u",
        default="https://nespresso.com/tw/en/order/capsules/vertuo",
        help="Listing page URL to start scraping (default the Vertuo listing)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="data.json",
        help="Output JSON file path (default: data.json)",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        _, products, _, capsule_ranges = get_main_list(args.url)
        simple_data = extract_simple_data(domain, products, capsule_ranges)
        save_data(simple_data, args.output)
    except Exception as exc:
        logging.error("Error: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
