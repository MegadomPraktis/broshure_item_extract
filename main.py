#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
from pathlib import Path
from urllib.parse import urljoin

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup
import pandas as pd

# ─── Paths(change based on your PC, avoid spaces between words) ─────────────────────────────
template_input  = Path(r"C:\extractor\broshura.bg.pdf")
template_output = Path(r"C:\extractor\цени_и_кодове_от_линкове.xlsx")

def get_output_path(base_path: Path) -> Path:
    candidate = base_path
    counter = 1
    while candidate.exists():
        stem, suffix = base_path.stem, base_path.suffix
        candidate = base_path.parent / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate

def extract_links_from_pdf(pdf_path: Path) -> list[str]:
    """Grab all unique http(s) URLs from annotations or visible text."""
    doc = fitz.open(pdf_path)
    links = set()
    for page in doc:
        for l in page.get_links():
            uri = l.get("uri")
            if uri and uri.startswith("http"):
                links.add(uri)
        text = page.get_text()
        for u in re.findall(r'https?://[^\s\)]+', text):
            links.add(u)
    return list(links)

def parse_single_product(soup: BeautifulSoup) -> dict | None:
    # — invcode —
    invcode = None
    label = soup.find(lambda tag: tag.name=='span' and 'Прод. код' in tag.get_text())
    if label:
        code_span = label.find_next_sibling('span')
        if code_span:
            invcode = code_span.get_text(strip=True)

    # — price —
    price = None
    buy_card = soup.find(id='product-buy-card')
    if buy_card:
        price_num = buy_card.find('span', class_=lambda c: c and 'text-3xl' in c)
        if price_num:
            price = price_num.get_text(strip=True)
            unit = price_num.find_next_sibling('span')
            if unit:
                price += ' ' + unit.get_text(strip=True)

    if invcode and price:
        return {"invcode": invcode, "price": price}
    return None

def fetch_product_data(url: str) -> list[dict]:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    # 1) try single product
    single = parse_single_product(soup)
    if single:
        return [single]

    # 2) fallback → look for the grid of cards
    cards = soup.select("div.grid.place-items-center > div.flex.flex-col.relative")
    results = []
    for c in cards:
        a = c.select_one("a[title][href]")
        if not a:
            continue
        href = a["href"]
        full_url = urljoin(url, href)
        # fetch detail page for each card
        try:
            r2 = requests.get(full_url, timeout=10)
            r2.raise_for_status()
            soup2 = BeautifulSoup(r2.text, 'html.parser')
            item = parse_single_product(soup2)
            if item:
                results.append(item)
            else:
                print(f"Warning: no data on detail page {full_url}")
        except Exception as e:
            print(f"Error fetching detail {full_url}: {e}")
    return results

def main():
    links = extract_links_from_pdf(template_input)
    print(f"Discovered {len(links)} links in brochure.")
    all_items = []

    for url in links:
        try:
            items = fetch_product_data(url)
            print(f"{url}: found {len(items)} item(s)")
            all_items.extend(items)
        except Exception as e:
            print(f"Error fetching {url}: {e}")

    if not all_items:
        print("No products extracted.")
        return

    # save to Excel
    df = pd.DataFrame(all_items)
    out_path = get_output_path(template_output)
    df.to_excel(out_path, index=False)
    print(f"Saved {len(df)} records to {out_path}")

if __name__ == '__main__':
    main()
