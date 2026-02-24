import spclipbd

def print_clipboard():
    bd = spclipbd.ClipboardContent()
    print(f'Suffix: [{bd.get_suffix()}], Length: {len(bd.get_raw())}')
    print('Content[:100]:', bd.get_raw()[:100])
    print('-' * 20)


def read_bin(filename: str) -> bytes:
    with open(filename, 'rb') as f:
        raw = f.read()
    return raw

def test_plaintext():
    print('test plaintext:')
    spclipbd.copy_to_clipboard('_plaintext', '你好hello'.encode('utf-8'))
    print_clipboard()
    input('next...')

def test_txt():
    print('test txt:')
    spclipbd.copy_to_clipboard('txt', '你好hello'.encode('utf-8'))
    print_clipboard()
    input('next...')

def test_png():
    print('test png:')
    spclipbd.copy_to_clipboard('png', read_bin('test.png'))
    print_clipboard()
    input('next...')

def test_jpg():
    print('test jpg:')
    spclipbd.copy_to_clipboard('jpg', read_bin('test.jpg'))
    print_clipboard()
    input('next...')

if __name__ == '__main__':
    test_plaintext()
    test_txt()
    test_png()
    test_jpg()
