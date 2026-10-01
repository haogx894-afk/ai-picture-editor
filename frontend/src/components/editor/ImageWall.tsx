import type { Asset, AssetKind } from '@/api/assets'
import MicroThumbnail from '@/components/MicroThumbnail'

const KIND_LABELS: Record<AssetKind, string> = {
  original: '原图',
  generated: '生成',
  subject: '主体',
  background: '背景',
  mask: '遮罩',
  marketing: '营销',
  export: '导出',
}

/** 会话内全部图片，含未采用的候选。点击切换画布当前图，不覆盖任何已有结果。 */
export default function ImageWall({
  assets,
  currentId,
  disabled,
  onPick,
}: {
  assets: Asset[]
  currentId: string
  disabled: boolean
  onPick: (assetId: string) => void
}) {
  return (
    <div className="border-line bg-paper shrink-0 border-t">
      <div className="scrollbar-slim flex scroll-px-4 items-center gap-2 overflow-x-auto px-4 py-3">
        {assets
          .filter((asset) => asset.kind !== 'mask')
          .filter(
            (asset) =>
              asset.id === currentId || (asset.kind !== 'subject' && asset.kind !== 'background'),
          )
          .map((asset) => {
          const active = asset.id === currentId
          return (
            <MicroThumbnail
              key={asset.id}
              asset={asset}
              active={active}
              disabled={disabled || active}
              onClick={() => onPick(asset.id)}
              title={
                active
                  ? `当前画布 · ${KIND_LABELS[asset.kind]}`
                  : `采用这张 · ${KIND_LABELS[asset.kind]} ${asset.width}×${asset.height}`
              }
              label={KIND_LABELS[asset.kind]}
            />
          )
        })}
      </div>
    </div>
  )
}
