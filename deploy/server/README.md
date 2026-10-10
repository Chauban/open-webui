# 服务器端文件备份

2026-10-02 从现网（rightwrite.cc）原样拷下来的。以前这些文件只存在服务器上，本地没有任何副本。

用途有两个：搭新机器（哈工深实例，见 [哈工深部署流程](../../docs/deployment/哈工深部署流程.md) §三）时照着装；现网服务器整台丢失时能重建。

**这里是副本，不是源头。** 改服务器上的文件之后，记得把这里也同步更新。`deploy/deploy.sh` 不会自动同步这些文件（它只管 `remote.sh`）。

## 不在这里的东西（含密钥，不能拷下来）

| 文件                             | 说明                                                                                           |
| -------------------------------- | ---------------------------------------------------------------------------------------------- |
| `/opt/rightwrite/rightwrite.env` | 模板见 [部署流程](../../docs/deployment/部署流程.md) §四；密钥在新机器上用 `openssl rand` 生成 |
| `/opt/rightwrite/.cos.yaml`      | 异地备份凭据。启用方法见 `offsite.sh` 文件末尾的注释                                           |

## 文件对照

| 本地                                          | 服务器路径                                                        | 属主 / 权限 | 哪些地方要按实例修改                                                                                                      |
| --------------------------------------------- | ----------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------- |
| `opt/migrate.sh`                              | `/opt/rightwrite/migrate.sh`                                      | root / 755  | 无                                                                                                                        |
| `opt/build.sh`                                | `/opt/rightwrite/build.sh`                                        | root / 755  | 无                                                                                                                        |
| `opt/backup.sh`                               | `/opt/rightwrite/backup.sh`                                       | root / 755  | 无                                                                                                                        |
| `opt/offsite.sh`                              | `/opt/rightwrite/offsite.sh`                                      | root / 755  | 注释里的桶名；`PREFIX` 的路径前缀 `rightwrite/`（见下文）                                                                 |
| `opt/deps.sh`、`opt/deps2.sh`                 | `/opt/rightwrite/`                                                | root / 755  | 无。这两个是首次安装依赖用的一次性脚本                                                                                    |
| `systemd/rightwrite.service`                  | `/etc/systemd/system/`                                            | root / 644  | 无                                                                                                                        |
| `systemd/rightwrite-backup.service`、`.timer` | `/etc/systemd/system/`                                            | root / 644  | 无                                                                                                                        |
| `nginx/rightwrite`                            | `/etc/nginx/sites-available/rightwrite`（软链到 `sites-enabled`） | root / 644  | `server_name` 和证书路径。这份是 certbot 改写过的版本；新机器建议先只写 80 端口的 server 块，再让 certbot 自己生成 443 段 |
| `nginx/upgrade-map.conf`                      | `/etc/nginx/conf.d/upgrade-map.conf`                              | root / 644  | 无                                                                                                                        |

## 哈工深实例的异地备份

`offsite.sh` 里的 `PREFIX="rightwrite/..."` 和现网 CAM 策略里的资源路径 `.../rightwrite/*` 是对应的。哈工深那台机器有两种做法：

- **用新机器自带的轻量对象存储桶**（推荐）：改桶别名所指向的桶，`PREFIX` 可以不改；再建一个新的 CAM 子用户，策略照抄现网，只把桶名换掉。
- **共用现网的桶**：`PREFIX` 改成 `hitsz/...`，新建一个 CAM 子用户，策略里的资源路径只写 `.../hitsz/*`。

两种做法的凭据都**不能和现网共用**。
