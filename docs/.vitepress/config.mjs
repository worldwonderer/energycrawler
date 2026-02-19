import {defineConfig} from 'vitepress'
import {withMermaid} from 'vitepress-plugin-mermaid'

// https://vitepress.dev/reference/site-config
export default withMermaid(defineConfig({
    title: "EnergyCrawler 文档",
    description: "仅保留 xhs 与 x 的精简版数据采集与自动化框架。",
    lastUpdated: true,
    base: '/',
    themeConfig: {
        search: {
            provider: 'local'
        },
        // https://vitepress.dev/reference/default-theme-config
        nav: [
            {text: '首页', link: '/'},
        ],

        sidebar: [
            {
                text: 'EnergyCrawler 使用文档',
                items: [
                    {text: '基本使用', link: '/'},
                    {text: '项目架构文档', link: '/项目架构文档'},
                    {text: '常见问题汇总', link: '/常见问题'},
                    {text: 'IP代理使用', link: '/代理使用'},
                    {text: '词云图使用', link: '/词云图使用配置'},
                    {text: '项目目录结构', link: '/项目代码结构'},
                    {text: '手机号登录说明', link: '/手机号登录说明'},
                ]
            },
        ],
    }
}))
