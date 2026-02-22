根据以下要求编写 `spclipbd.py`:

## 功能要求

1. 设计类型 `ClipboardContent`, 它表示剪贴板中的内容，可能是文本、图片或文件.
    - 此类型需包含 get_suffix() 方法，返回一个 `str`, 表示此对象构造时读取到的剪贴板中的文件后缀, 如果剪贴板是纯文本, 返回 `"_plaintext"`.
    - 此类型需包含 get_raw() 方法, 返回一个 `bytes`, 表示此对象构造时读取到的剪贴板中的文件的二进制内容, 如果剪贴板是纯文本，返回的 `bytes` 对象以 `utf-8` 编码.
    - 此类型的对象在构造时 (`__init__` 方法调用时) 读取剪贴板中的内容.


2. `ClipboardContent` 在 `Windows`, `MacOS` 和 `Linux(with xclip)` 上都用统一的接口, 要能正确给出结果.
    - 在 `Windows` 上, 借助自带的 PowerShell 直接调用 .NET 框架的底层 API 实现.
    - 在 `MacOS` 上, 借助自带的 AppleScript 实现.
    - 在 `Linux` 上, 借助 xclip 工具实现.

3. 编写 `copy_to_clipboard` 函数.
    - 功能是将某些内容写入剪贴板.
    - 第一个参数接收待写入内容的类型, 是一个 `str` 对象，含义同 `ClipboardContent` 的 `get_suffix` 方法返回值.
    - 第二个参数接收待写入内容的二进制内容数据, 是一个 `bytes` 对象, 含义同 `ClipboardContent` 的 `get_raw` 方法返回值.


## 其他要求

1. 遵循的 Python 版本是 Python 3.13.

2. 编写 `test.py` 作为测试程序, 测试 `spclipbd.py` 的正确性.

3. 步骤: 编写 `spclipbd.py` -> 编写并运行 `test.py` -> 修改 `spclipbd.py` -> 编写并运行 `test.py` -> ... 如此重复，直到做好.

4. 类文档和函数文档, 按照业界流行标准编写, 用英文编写.
