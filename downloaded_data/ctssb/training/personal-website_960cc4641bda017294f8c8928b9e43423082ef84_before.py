import sys
import mistune
import getopt
import pystache
import shutil
import git
import datetime
import pathlib
import re


def main(argv):
    posts_folder, output_folder = parse_arguments(argv)
    posts_path = pathlib.Path(posts_folder)
    output_path = pathlib.Path(output_folder)
    build_blog(posts_path, output_path)
    render_template('index', {'title': 'Home', 'index': True}, output_path / 'index.html')


def parse_arguments(argv):
    """
    Parses the command line arguments passed to the program. The allowed flags
    are:
        -h, --help: Shows the usage instructions of the program.
        -p, --posts <directory>: The directory to read posts from.
        -o, --output <directory>: The directory to output html to.

    If the arguments don't match the specification the usage instructions
    for the program is shown.

    :param argv: A list of command line arguments.
    :return: A folder to read posts from and a folder to output html to.
    """
    try:
        opts, args = getopt.getopt(argv, 'hp:o:', ['help', 'posts=', 'output='])
    except getopt.GetoptError:
        invalid_arguments()

    posts = ''
    output = ''

    for opt, arg in opts:
        if opt in ('-h', '--help'):
            print_usage_instructions()
            sys.exit()
        elif opt in ('-p', '--posts'):
            posts = arg
        elif opt in ('-o', '--output'):
            output = arg

    if posts == '' or output == '':
        invalid_arguments()

    return posts, output


def invalid_arguments():
    """
    Prints the usage instructions for the program and exits with error code 2.
    """
    print_usage_instructions()
    sys.exit(2)  # Exit code 2 = command line syntax error


def print_usage_instructions():
    """
    Prints the usage instructions for the program.
    """
    print('parse_posts.py usage:\n')
    print('\t-h, --help: Shows the usage instructions of the program')
    print('\t-p, --posts <directory>: The directory to read posts from.')
    print('\t-o, --output <directory>: The directory to output html to.')


def build_blog(posts_path, output_path):
    """
    Goes through the posts folder, parses all posts and copies the rendered
    html to the output folder. Posts must have the file ending .markdown.
    All non-post files will be copied to the output folder without modification.

    :param posts_path: The folder to read posts from. If this folder doesn't
                         exist the script will exit without doing anything.
    :param output_path: The folder to output html to. Will be created if it
                          doesn't exist.
    """
    if not posts_path.exists():
        print('Error: Folder {} does not exist.'.format(str(posts_path)))
        sys.exit(2)

    files = list(posts_path.glob('**/*.markdown'))
    # Ignore all files and folders that start with an underscore.
    ignore = list(posts_path.glob('**/_*.markdown')) + list(posts_path.glob('**/_*/*.markdown'))

    posts = [parse_post(file, posts_path) for file in files if not file in ignore]
    posts.sort(key=lambda post: post['date'], reverse=True)

    url_prefix = 'posts'

    for i, post in enumerate(posts):
        data = {
            'title': post['title'],
            'post': post,
            'url_prefix': url_prefix,
            'blog': True
        }

        if not i == 0:
            data['next'] = posts[i - 1]
        if not i == len(posts) - 1:
            data['prev'] = posts[i + 1]

        render_template('blog_post', data, output_path / 'posts' / post['url'] / 'index.html')

    posts[-1]['last'] = True

    render_template('blog_index', {
        'blog': True,
        'title': 'Blog',
        'posts': posts,
        'url_prefix': url_prefix
    }, output_path / 'blog' / 'index.html')


def parse_post(full_path, root_path):
    """
    Parses a post written in markdown with optional metadata from a file.

    :param dir_entry: A directory entry for the post file to parse.
    :returns: A dictionary representing a single post.
    """
    file_content = full_path.read_text()
    segments = file_content.split('\n\n')

    metadata = dict()
    if not segments[0].startswith('# '):
        # File didn't start with title -> there is metadata.
        metadata = parse_metadata(segments[0])
        segments = segments[1:]

    markdown = mistune.Markdown()

    title = segments[0].replace('# ', '')
    first_paragraph = markdown(segments[1])
    content = markdown('\n\n'.join(segments[2:]))

    # This regex matches all headings and captures their level and their text.
    regex = re.compile('<h(.)>(.*)<\/h\\1>')
    for match in re.finditer(regex, content):
        h_number = match.group(1)
        heading = match.group(2)
        anchor = '{0}'.format(heading.lower().replace(' ', '_'))

        formatted_heading = '<h{0}><a name="{1}" href="#{1}">{2}</a></h{0}>'.format(h_number, anchor, heading)

        content = content.replace(match.group(0), formatted_heading)

    # A simpler way to add links to headings. Though with this method you can't
    # change the string captured by group 2 from what I can tell.
    # content = regex.sub('<h\\1><a href="#\\2">\\2</a></h\\1>', content)

    repo = git.Repo(root_path.parts[0])

    try:
        latest_commit = next(repo.iter_commits(paths=full_path.name))
        date = datetime.date.fromtimestamp(latest_commit.authored_date)
    except StopIteration:
        date = datetime.date.today()

    url = str(full_path.relative_to(root_path).with_suffix('')).lower().replace(' ', '_')

    post = metadata.copy()
    post.update({
        'date': date,
        'title': title,
        'first_paragraph': first_paragraph,
        'content': content,
        'url': url
    })

    return post


def parse_metadata(block):
    """
    Parses a block of metadata. Metadata attributes are divided into key and
    value, separated by a colon and a space, with one attribute per line. Values
    can be either single values or comma separated lists. If a value is a comma
    separated list it will be converted to a list object, otherwise it will be
    a simple string.

    :param block: A string with a block of metadata.
    :return: A dictionary of all key-value pairs found in a metadata block.
    """
    metadata = dict()
    lines = block.split('\n')
    for line in lines:
        key, value = line.split(': ')
        values = value.split(', ')
        if len(values) > 1:
            metadata[key] = values
        else:
            metadata[key] = value

    return metadata


def render_template(template, data, path):
    """
    Renders a template with data and writes the result to a new file.

    :param template: The name of the template to use when rendering.
    :param data: The data to use when rendering.
    :param path: The path to write the rendered file to.
    """
    path = pathlib.Path(path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True)

    renderer = pystache.Renderer(search_dirs='templates')
    body = renderer.render_name(template, data)
    html = renderer.render_name('main', {'body': body, 'data': data})
    path.write_text(html)


if __name__ == '__main__':
    main(sys.argv[1:])
