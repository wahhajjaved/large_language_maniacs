import get_data
import os
from get_data import download_raw_dataset, convert_to_faces
import argparse

site_url_dict = {
    'danbooru' : 'https://danbooru.donmai.us/posts?tags={}'
}

def download_dataset(tag, n_images, download_url, out_dir, site_name):
    download_raw_dataset(tag, n_images, download_url=download_url)
    in_dir = os.path.join("data/raw/", site_name)
    out_dir = os.path.join("data", out_dir, site_name)
    print(out_dir)
    convert_to_faces(tag, in_directory=in_dir, out_directory=out_dir)

if __name__ == '__main__':
    parser = argparse.ArgumentParser("Downloads anime pictures, then crops faces into a seperate directory.")
    parser.add_argument('-s', '--site', action='store', default = "danbooru", help="Name of the site to download from, ex. Danbooru")
    parser.add_argument('-n', '--number', action='store', type=int, default="1000", help="Number of images to download")
    parser.add_argument("tag", action='store', help="Tag to search for")
    parser.add_argument('-d', '--dir', action='store', default="faces", help="Directory that processed faces are stored")
    args = parser.parse_args()

    if args.site not in site_url_dict.keys():
        raise RuntimeError("Site not supported!")

    site_url = site_url_dict[args.site]
    download_dataset(args.tag, args.number, site_url, args.dir, args.site)
